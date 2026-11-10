# Answer language eval

Measures how often the system answers in the language of the question (`BUG-11`). It asks a fixed set of questions through the real agent graph and scores the answers with the same deterministic detector the API uses (`src/services/language.py`).

It is not part of `uv run pytest`, and `--run-evals` does not collect it either. Each measurement costs real LLM calls.

## What it needs

- The development database with the corpus, started with `docker compose up -d`. `DATABASE_URL` in `.env` must point at it, not at the test database on port 5439; the runner refuses that port.
- A working `ANTHROPIC_API_KEY` in `.env`.
- The id of the tenant that owns the corpus. In the backup of 2026-09-16, `11111111-1111-1111-1111-111111111111` has the CV and the 128 knowledge graph triples.

## Cost

There are 20 questions (`questions.json`) and 5 repetitions by default, so 100 answers per variant. Each answer is 2 or 3 LLM calls: supervisor, generator, and a second generator pass when the reviewer retries. A variant is about 200-300 calls, and a before/after comparison about 500. The runner prints the estimate before it starts.

## Run it

Collect the answers of the current code:

```sh
uv run --no-sync python tests/evals/answer_language/collect.py \
    --tenant 11111111-1111-1111-1111-111111111111 --out after.jsonl
```

To check the setup first, use one question and one repetition (`--only betterfly-en --repeats 1`).

Collect the answers of another version, such as the commit before a change, from a worktree. Only `src/` comes from the worktree; the `.env`, the questions and the runner are this checkout's:

```sh
git worktree add --detach /tmp/wt_before "$(git merge-base develop HEAD)"
uv run --no-sync python tests/evals/answer_language/collect.py \
    --code-root /tmp/wt_before \
    --tenant 11111111-1111-1111-1111-111111111111 --out before.jsonl
git worktree remove /tmp/wt_before
```

Score them. This makes no LLM call, so you can score again after changing the detector:

```sh
uv run --no-sync python tests/evals/answer_language/score.py after.jsonl --baseline before.jsonl
```

## Reading the report

- **Rate** is `matches / (matches + mismatches)`, with a Wilson 95% interval. Undetermined answers (too short or too close to call) and errors are counted apart and never as matches. A language with nothing determined has no rate.
- **Supervisor decision** is how often `answer_language` matched the question's expected language. It is `n/a` for code that has no such field.
- **Verdict:** any drop is a *regression*. A rise is an *improvement* only when the two intervals do not overlap; otherwise it is *no evidence of improvement*.
- Read every mismatch and undetermined answer in the JSONL before reporting the numbers: the detector can be wrong on short answers full of English technology names.

The runner calls the graph directly, not the HTTP API, so it skips the semantic cache and writes nothing to the database.
