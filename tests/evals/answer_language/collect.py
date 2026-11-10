"""Collects answers for the answer language eval through the real graph (BUG-11).

    uv run --no-sync python tests/evals/answer_language/collect.py \\
        --tenant 11111111-1111-1111-1111-111111111111 --out after.jsonl

It calls the agent graph directly, not the HTTP API: that skips the semantic cache
(so every repetition really runs), memory extraction and the evaluator, and the run
reads the database but writes nothing to it. Each answer costs 2-3 LLM calls.

`--code-root` points at another checkout (a `git worktree` of the commit before the
change) to collect answers with that code. Only `src` comes from there: the `.env`,
the question set and this runner are always this repository's, so both variants run
against the same database with the same questions. Scoring is a separate step
(score.py), so this script imports nothing that the old code lacks.

It is not a pytest test: tests/conftest.py would point it at the disposable database
on port 5439, which has no corpus.
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[3]
QUESTIONS = Path(__file__).resolve().parent / "questions.json"
TEST_DB_PORT = 5439


def code_version(root: Path) -> str:
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip() or "unknown"
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "src"],
                           capture_output=True, text=True).stdout.strip()
    return f"{sha}+dirty" if dirty else sha


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Collect answers for the answer language eval.")
    parser.add_argument("--tenant", type=uuid.UUID, required=True, help="Tenant that owns the corpus")
    parser.add_argument("--out", type=Path, required=True, help="JSONL to write; must not exist")
    parser.add_argument("--code-root", type=Path, default=REPO, help="Checkout whose src/ answers")
    parser.add_argument("--repeats", type=int, default=5, help="Times each question is asked")
    parser.add_argument("--concurrency", type=int, default=4, help="Graph runs at the same time")
    parser.add_argument("--top-k-retrieve", type=int, default=15)
    parser.add_argument("--top-k-rerank", type=int, default=10)
    parser.add_argument("--only", nargs="+", metavar="ID", help="Ask only these question ids")
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    return parser.parse_args(argv)


def database_target() -> str:
    """Host and port of DATABASE_URL, without credentials. Refuses the test database."""
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if url.port == TEST_DB_PORT:
        sys.exit(f"DATABASE_URL points at port {TEST_DB_PORT}, the disposable test database: it has no corpus.")
    return f"{url.hostname}:{url.port}{url.path}"


async def collect(args, questions, out):
    # Imported here, after the code root and the .env are in place.
    from src.services.agent_graph.graph import build_graph
    from src.services.db import close_pool

    graph = build_graph()
    code = code_version(args.code_root)
    semaphore = asyncio.Semaphore(args.concurrency)
    jobs = [(q, r) for r in range(args.repeats) for q in questions]
    done = 0

    async def run(question, repeat):
        nonlocal done
        state = {
            "messages": [], "tenant_id": args.tenant, "user_profile": "",
            "query": question["query"], "history": question["history"],
            "top_k_retrieve": args.top_k_retrieve, "top_k_rerank": args.top_k_rerank,
            "intent_type": "", "search_queries": [], "documents": [], "final_answer": None,
            "iterations": 0, "needs_more_info": False,
        }
        record = {"id": question["id"], "language": question["language"], "repeat": repeat,
                  "query": question["query"], "code": code,
                  "top_k": [args.top_k_retrieve, args.top_k_rerank]}
        async with semaphore:
            started = time.perf_counter()
            try:
                final = await graph.ainvoke(state)
                answer = final.get("final_answer")
                record.update(answer=answer.answer if answer else None,
                              answer_language=final.get("answer_language") or None,
                              intent_type=final.get("intent_type"),
                              documents=len(final.get("documents") or []),
                              iterations=final.get("iterations"), error=None)
            except Exception as e:
                record.update(answer=None, answer_language=None, error=f"{type(e).__name__}: {e}"[:300])
            record["seconds"] = round(time.perf_counter() - started, 2)
        # One line per answer as it finishes: an interrupted run keeps what it paid for.
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()
        done += 1
        print(f"[{done}/{len(jobs)}] {record['id']} #{repeat}"
              f"{' ERROR ' + record['error'] if record['error'] else ''}", file=sys.stderr)

    try:
        await asyncio.gather(*(run(q, r) for q, r in jobs))
    finally:
        await close_pool()


def main(argv=None) -> int:
    args = parse_args(argv)
    args.code_root = args.code_root.resolve()
    if args.out.exists():
        sys.exit(f"{args.out} already exists; pick another name so no paid answers are overwritten.")

    # The .env before any import of src: since HYG-05, src/config.py loads it, but a
    # --code-root from before that fix builds its Anthropic clients without a key.
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
    sys.path.insert(0, str(args.code_root))
    import src
    # src is a namespace package: every sys.path entry with a src/ folder joins it, so
    # all of them must be the code root's, or modules would mix two versions.
    roots = [Path(p).resolve() for p in src.__path__]
    if not all(root.is_relative_to(args.code_root) for root in roots):
        sys.exit(f"src resolves to {', '.join(map(str, roots))}, not only to {args.code_root}")

    questions = json.loads(args.questions.read_text())["questions"]
    if args.only:
        questions = [q for q in questions if q["id"] in set(args.only)]
        missing = set(args.only) - {q["id"] for q in questions}
        if missing:
            sys.exit(f"Unknown question ids: {', '.join(sorted(missing))}")

    print(f"Code {code_version(args.code_root)} from {args.code_root}", file=sys.stderr)
    print(f"Database {database_target()}, tenant {args.tenant}", file=sys.stderr)
    print(f"{len(questions)} questions × {args.repeats} = {len(questions) * args.repeats} answers "
          f"(~{len(questions) * args.repeats * 2}-{len(questions) * args.repeats * 3} LLM calls)", file=sys.stderr)

    started = time.perf_counter()
    with args.out.open("w") as out:
        asyncio.run(collect(args, questions, out))
    print(f"Done in {time.perf_counter() - started:.0f} s: {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
