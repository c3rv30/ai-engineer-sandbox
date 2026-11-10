# 🔎 Technical Audit: Divergences, Defects and Debt

> **Date:** 2026-09-10
> **Branch audited:** `develop` (base commit `a9e8eaf`, with `pyproject.toml` and `uv.lock` modified and uncommitted)
> **Environment verified:** Python 3.14.0 · `anthropic` 1.4.0 · `instructor` 1.16.0 · `langgraph` 1.2.11 · `pyjwt` 2.13.0 · `numpy` 2.5.2

> **Translation note (2026-11-09).** This audit was written in Spanish and translated to English together with the rest of the repository. Some names changed in that pass, and this document uses the current ones: the demo user `empresa_x` is now `company_x` (same tenant, `11111111-…`); `docs/AUDITORIA_TECNICA.md` is now `docs/TECHNICAL_AUDIT.md`; the English paper `PAPER_EN.md` is now `docs/PAPER.md` and the Spanish one was removed; `docs/history/FASE_4_*.md` and `ROADMAP_FASE_5_ESCALABILIDAD.md` are now `PHASE_4_*.md` and `ROADMAP_PHASE_5_SCALABILITY.md`; and `tests/api/dobles.py` is now `tests/api/doubles.py`. The questions used in the measurements were asked in Spanish, the language of the corpus, and are quoted that way with a translation. Code excerpts from the snapshot are quoted literally, Spanish strings and comments included. Messages from code written after it, such as `Internal error (<id>)` (then `Error interno (<id>)`), are quoted with their current English text. Commit hashes point to the rewritten history.

## Scope and method

The whole repository was audited:

| Surface | Volume | Coverage |
|---|---|---|
| Documentation | 11 files (`README.md`, `CONTEXT.md`, `ARCHITECTURE.md`, 8 in `docs/`) | Read in full, including the Spanish `PAPER.md` (478 lines) and `PAPER_EN.md` (496 lines) |
| Source code | 24 files, 1,694 lines in `src/` | Read in full |
| Data schema | 7 scripts in `sql/` | Read in full |
| Build and infrastructure | `pyproject.toml`, `uv.lock`, `docker-compose.yml`, `.env.example`, `.gitignore` | Read in full |
| Tests and loose scripts | `tests/test_rag.py`, `src/pipeline.py`, 6 scripts in the root | Read in full |

**Method.** Every claim in the documentation was checked against the code that implements it. Every finding includes: exact location (`file:line`), the literal code excerpt, a reproducible verification command and a proposed patch. The system was not run (Postgres was not started and the Anthropic API was not called); all the evidence is static and can be verified with `grep`, `cat` and reading the source.

**Relation to the existing documentation.** [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) is a post-mortem of six problems already solved. [`ROADMAP_PHASE_5_SCALABILITY.md`](history/ROADMAP_PHASE_5_SCALABILITY.md) plans five future epics. `PAPER_PLAN.md` §5 lists six known and accepted limitations. **This document covers the gap between the three**: what is broken or divergent *now*, unsolved and unplanned.

## Overall assessment

The project is architecturally sound. The LangGraph graph is well decomposed, two-stage retrieval is implemented correctly (RRF with `k=60` fusing HNSW and FTS, followed by a cross-encoder), the statistical semantic chunking is real and mathematically correct, and the RLS policies are well written. The formalization in `PAPER.md` is rigorous and mostly faithful.

The value of this audit is not in questioning the design but in recording three things:

1. **The migration to Phase 4 left orphaned code and outdated documentation.** Adopting LangGraph replaced the linear pipeline, but several pieces of the old one are still documented as current (`DOC-01`, `BUG-06`) and others were left disconnected (`BUG-03`).
2. **The papers claim verifiable properties the code does not have.** In a portfolio repository this has a specific cost: whoever checks the paper against the source will find the difference (`DOC-02`, `PERF-01`).
3. **Multi-tenant isolation, the project's central argument, can be defeated with two lines of code.** The RLS policies work; the entry into the system can be forged (`SEC-01`, `SEC-02`).

---

## 1. Executive Summary

| Category | 🔴 Critical | 🟠 High | 🟡 Medium | ⚪ Low | Total |
|---|:---:|:---:|:---:|:---:|:---:|
| Doc ↔ code divergences | — | 3 | 4 | 1 | **8** |
| Functional defects | — | 5 | 3 | — | **8** |
| Security | 2 | 1 | 1 | — | **4** |
| Performance | — | 2 | 2 | — | **4** |
| Repository hygiene | — | — | 2 | 2 | **4** |
| **Total** | **2** | **11** | **12** | **3** | **28** |

> **After the snapshot.** These are not added to this count, which is the state on 2026-09-10. All of them turned up while verifying fixes against the real system and are in the index (§2) and in the remediation table:
> - `BUG-09` (🟠), on 2026-09-13, while rewriting the streaming loop for `DOC-01`.
> - `SEC-05` (🟠), `SEC-06` (🟡), `BUG-10` (🟠), `HYG-05` (🟡) and `HYG-06` (⚪), on 2026-09-14.
> - `HYG-07` (🟡), on 2026-09-15, while implementing the `SEC-05` patch.
> - `HYG-08` (🟠), on 2026-09-16, while reviewing the state of Docker.
> - `SEC-07` (🟠), on 2026-09-16, while fixing `HYG-07`.
> - `HYG-09` (⚪), on 2026-09-17, while closing the API regression layer.
> - `HYG-10` (🟠), on 2026-11-09, while verifying `HYG-01` from a clean clone.
> - `BUG-12` (🟠), on 2026-11-10, while preparing the measurement of the answer language change (`BUG-11`).

### Severity criteria

| Level | Definition applied |
|---|---|
| 🔴 **Critical** | Lets an attacker read or destroy another tenant's data. Blocks any deployment. |
| 🟠 **High** | Breaks advertised functionality, corrupts stored data, or measurably degrades the system under normal load. |
| 🟡 **Medium** | Verifiable divergence between documentation and code, or a defect with limited impact and no corruption. |
| ⚪ **Low** | Cosmetic or maintenance debt with no functional impact. |

### The five findings to address first

| # | ID | Why first |
|:---:|---|---|
| 1 | `SEC-01` | The JWT `SECRET_KEY` is hardcoded and committed. HS256 is symmetric: whoever reads the repo can sign tokens with any `tenant_id`. It defeats the whole isolation model. **5 minutes to fix.** |
| 2 | `SEC-02` | `tenant_id` is interpolated with an f-string into `SET app.current_tenant` without validation. Chained with `SEC-01`, it is SQL injection with `ALL` privileges on the database. **5 minutes to fix.** |
| 3 | `BUG-01` | The semantic cache stores the answer polluted with the stream's progress messages. It corrupts data cumulatively: every hit serves a fake execution trace. |
| 4 | `BUG-03` | The conversation history never reaches the graph. Coreference resolution is written, tested and unreachable. Reconnecting it means passing one field along. |
| 5 | `DOC-01` | The token-by-token streaming the README sells as a headline feature has not existed since the migration to LangGraph. It is the divergence most visible to an outside reader. |

> **Before those five:** `BUG-08` leaves the application permanently unable to start when `/tmp` loses the re-ranker cache. It takes two minutes, and none of the above can be verified until it is solved.

### Remediation status

This document is a snapshot of the state on the date in the header. The inventories, the trace and the appendices (§3, §9 and §11–§14) describe that snapshot and are not rewritten with each fix: some of their rows are no longer true, such as the one on `PAPER.md` §5.4 about `BUG-05`. **The current status of each finding is the one in this table and in its `Status:` line.** What has been fixed since:

| Finding | Status | Date | Verification |
|---|:---:|:---:|---|
| `BUG-08` | ✅ fixed | 2026-09-11 | Persistent cache + automatic cleanup; tested with a healthy cache, a corrupt one and an override |
| `SEC-01` | ✅ fixed | 2026-09-11 | `JWT_SECRET_KEY` required from the environment, at least 32 characters; token with the old key → 401 |
| `SEC-02` | ✅ fixed | 2026-09-11 | `tenant_id` typed as `uuid.UUID` at the edge; SQL injection in the token → 401; RLS verified against the real DB |
| `BUG-01` | ✅ fixed | 2026-09-11 | Stream object separated from the stored one; 4 of 8 polluted rows purged from `semantic_cache` |
| `BUG-03` | ✅ fixed | 2026-09-11 | History passed all the way to the supervisor; verified in 5 phases with a negative control |
| `BUG-03` (follow-up) | ✅ fixed | 2026-09-12 | The generator also gets the history; formatting shared in `history.py`. The answer to a follow-up goes from dumping 11 years of the résumé to one exact sentence |
| `DOC-01` | ✅ fixed | 2026-09-13 | Token-by-token streaming brought back through LangGraph's `custom` channel: 4 → 244 SSE events, first text 13.5 s → 9.6 s, measured against a real server |
| `BUG-09` | ✅ fixed | 2026-09-13 | New finding: the stream returned no answer for greetings, out-of-scope topics or tools. Fixed with `DOC-01` |
| `SEC-04` | ✅ fixed | 2026-09-14 | Temporary file with a random name; the original only as metadata. Negative control against a real uvicorn: 1/9 → 9/9 properties; real ingestion 8/8 |
| `SEC-03` | ✅ fixed | 2026-09-14 | Parameterized `ILIKE ANY($1::text[])`. With a permissive tokenizer, the old version falls to all three payloads, including a cross-tenant read; the new one, to none. Same results on 16 real queries |
| `BUG-02` | ✅ fixed | 2026-09-14 | Intent allowlist, plus confidence and `requires_more_info`, on both endpoints. Against a real server: 3/8 → 8/8. Before, *"¿Cuánto vale ethereum?"* ("How much is ethereum?") got the bitcoin price from the cache |
| `BUG-04` | ✅ fixed | 2026-09-14 | `00_create_app_user` → full `01_init`; `apply_*` to `sql/migrations/`; TCP healthcheck. From an empty volume: `exit=3` → `healthy`. Catalog identical to development (77/77), RLS 7/7, real app 6/6 |
| `BUG-06` | ✅ fixed | 2026-09-14 | `top_k` passed through to the researcher, with single defaults (15/10), range limits and no cache when they differ. Against a real server: 3/8 → 8/8; out of range 200 → 422 |
| `BUG-05` | ✅ fixed | 2026-09-14 | Option (a): each retry widens the window (15/10 → 30/15, capped at the API maximums) and there is no retry if widening cannot add anything. Against a real server: 3/7 → 7/7; identical retries 3 → 0 |
| `PERF-01` | ✅ fixed | 2026-09-15 | Single pool in `db.py` and transaction-local `set_config`. Connections per query 8 → 0; 25 concurrent queries: 7 `TooManyConnectionsError` → 0; isolation verified with a pool of 2 |
| `PERF-02` | ✅ fixed | 2026-09-15 | Single instance in `embeddings.py` with `to_pgvector`. Instances 4 → 1; API import 16.6 s → 5.6 s; *physical footprint* −102 MB (not 270–360 MB); identical results |
| `PERF-03` | ✅ fixed | 2026-09-15 | `chunk_text` and tools in `asyncio.to_thread`. Maximum `/health` wait: ingestion 1182 → 21 ms, tool 204 → 14 ms; 20-page PDF: event loop stall 1060 → 16 ms, same chunks |
| `PERF-04` | ✅ fixed | 2026-09-15 | `max_tokens` 300 → 1024, `reasoning` ≤ 600 characters and explicit `max_retries=3`. Real judge, 15 evaluations per variant: lost 10/15 → 0/15 |
| `DOC-02` | ✅ fixed | 2026-09-15 | `ge`/`le` on the three `RAGEvaluation` scores: a 1.2 fails in Pydantic (retryable) and not at the SQL `CHECK` (silent loss). Together with `PERF-04` |
| `DOC-03` | ✅ fixed | 2026-09-16 | Startup from a clean clone following only the README and `.env.example`. Before: it fails at step 2, and once completed the API connects as `postgres` and **`company_x` gets a fact from one of `bryan`'s documents**. After: it starts first time as `app_user`, and the same fact does not cross tenants (positive control: `bryan` does get it) |
| `HYG-08` | ✅ fixed | 2026-09-16 | Named volume `pgdata`, with the development database migrated without loss (cold copy, `diff -r` with no differences). Negative control with `compose down` + `up`: with the old compose file, the marker row disappears and the volume is orphaned; with the new one, it survives |
| `HYG-07` | ✅ fixed | 2026-09-16 | Line deleted from `00_create_app_user.sql` (together with the two `GRANT ... ON ALL` that did nothing) and the `apply_revoke_default_privileges.sql` migration for the existing database. New table in `public` created as `postgres`: `app_user` reads it → does not read it, in the development database and in one created from scratch. The five tables keep their privileges and a signed round trip works on all of them |
| `HYG-06` | ✅ fixed | 2026-09-16 | `restart: unless-stopped`. Immediate server crash in a disposable project: with the old compose file it stays `exited`; with the new one it comes back on its own (`restarts=1`), and a manual `docker stop` is still respected. The daemon restart was not reproduced |
| `BUG-10` | ✅ fixed | 2026-09-16 | First reproduced end to end (it lacked that): the follow-up of a conversation about Itaú/Kabeli got **literally** the answer from another one about MisterGas. With the patch, each answers its own referent and the cache records no wrongful hit |
| `SEC-06` | ✅ fixed | 2026-09-15 | The three points log the traceback and return `Internal error (<id>)`. Against a real server: the temporary file's absolute path and Anthropic's 401 go from reaching the client to existing only in the log, correlated by the identifier |
| `SEC-05` | ✅ fixed | 2026-09-15 | Signed tenant context (HMAC-SHA256) verified by a `SECURITY DEFINER` function. Against the real DB, as `app_user`: the finding's injection goes from reading **10 foreign triples to 0**; without a signature or with a fake one, 0 rows. Against the real API: with the right key, 4 sources and confidence 0.95; with a wrong one, 0 sources |
| `BUG-07` | ✅ fixed | 2026-09-16 | Two-layer regression suite, planned as an OpenSpec change (`regression-test-suite`). Layer 1, pure logic: 71 tests in ~0.3 s without DB, LLM or `.env`. Layer 2, disposable Postgres started by pytest: 18 tests in ~8 s, without touching the development database. Negative control: 22 of 22 reintroduced defects detected |
| API layer | ✅ added | 2026-09-17 | Third layer of the suite, with doubles for the graph and the services (OpenSpec change `api-regression-layer`): 40 tests without Docker that pin `SEC-01`, `SEC-02`, `SEC-06`, `BUG-01` and `BUG-09`. Negative control: 9 of 9. No production changes |
| `HYG-09` | ✅ fixed | 2026-09-17 | `onnxruntime` telemetry disabled before importing FlashRank, in `reranker.py` and in `tests/conftest.py`. The full suite goes from aborting 7 of every 8 times to 0 of 10; same re-ranking before and after |
| `HYG-01` | 🟡 partly fixed | 2026-11-09 | `pyjwt`, `numpy` and `python-multipart` declared. Clean clone following the README: `ModuleNotFoundError: No module named 'jwt'` → `111 passed` without Docker. Moving `deepeval` to `dev` is pending |
| `HYG-10` | ✅ fixed | 2026-11-09 | New finding. `.python-version` with `3.14`: `uv sync` on a clean clone goes from failing with `onnxruntime` having no wheels for 3.15 to installing with CPython 3.14.8 |
| `BUG-12` | ✅ fixed | 2026-11-10 | New finding. One lock around `model.encode`. Four simultaneous first requests to a freshly started API: before, the server hung (4 timeouts at 90 s) or died (exit 133), in 2 of 2 starts; after, 4 × 200 in 2 of 2. Four concurrent cold `embed()` calls: 0 of 5 → 10 of 10 |
| The other 9 from the snapshot | ⬜ open | — | — |
| `HYG-05` | ⬜ open | 2026-09-14 | New finding; see §2 and the plan (§10) |
| `SEC-07` | 🟡 layer 1 fixed | 2026-09-16 | New finding, found while fixing `HYG-07`. `GRANT CONNECT` instead of `GRANT ALL` on the database. Same attack with the real code: at `HEAD`, the victim's password ends up in an attacker's table without RLS; with the patch, `CREATE SCHEMA` is denied and the write goes to `public`. Layers 2 and 3 (the `ALTER ROLE` residue) remain open |

**Pending data decisions.** The fixed code no longer produces these two things, but they are still in the development database. They were not touched without the user deciding:

| # | What | Origin | Proposal |
|---|---|---|---|
| D-01 | The 22 rows of `documents` store the server's temporary path in `metadata.source` (`/var/folders/…/T/bbobadilla_resume.pdf`) | `SEC-04` | Keep only the file name: `UPDATE documents SET metadata = jsonb_set(metadata, '{source}', to_jsonb(regexp_replace(metadata->>'source', '^.*/', ''))) WHERE metadata->>'source' LIKE '/%';` as `postgres` |
| D-02 | A `semantic_cache` row (`7f55b002…`, `requires_more_info=true`, confidence 0.75) that the `BUG-02` policy would not store and that is still being served | `BUG-02` | Delete it |

**Corrections to the snapshot.** Verifying against the real system showed some claims in this document to be incomplete or wrong. The details are in each finding's status line:

- **`SEC-03`**: RLS was assumed to contain an injection in that query. It does not: `app_user` can rewrite its tenant from the statement itself (catalogued as `SEC-05`).
- **`SEC-04`**: the path traversal does not just overwrite the target; the `finally` deletes it. In addition, the proposed patch, applied alone, would have lost each document's original name.
- **`BUG-02`**: the cache did not just serve stale data, but another query's data (the bitcoin price to someone asking about ethereum). `out_of_scope` is not harmless. Since the `BUG-09` fix, `/chat/stream/` also cached tools.
- **`BUG-04`**: `FORCE ROW LEVEL SECURITY` does not protect the `postgres` DSN in `.env.example`, because a superuser bypasses RLS with or without `FORCE`.
- **`PERF-04`**: the evaluator did not always fail, as commit `1a35a4d` (`BUG-02`) says, but not just now and then either: with a realistic context of 10 documents it lost **10 of every 15** evaluations to `max_tokens`.
- **`PERF-01`**: the cross-tenant leak feared when reusing connections would not happen with asyncpg 0.31, whose `RESET ALL` when returning a connection clears the session tenant (measured). With an empty reset the leak does appear. Nor was it true that all nine access points used `app_user`: `ingestion.py` defaulted to the superuser.
- **`DOC-03`**: the security risk was real end to end, not just in theory: with the template, one tenant got through the API a fact from another's document. In addition, `SEC-05` had added a breakage the snapshot could not contain: the README started the database before creating `.env`, and Compose no longer starts without `TENANT_SIGNING_KEY`.
- **`BUG-10`**: the finding was catalogued as verified only by reading the code. Reproduced on 2026-09-16, it turned out to be exactly as described and something more: the answer served from the cache starts with *"Según el historial anterior"* ("According to the previous history"), attributing someone else's conversation to the user.
- **`SEC-05`**: the proposed patch (option 1) was not enough as described. Storing the key in a `public` table "without a `GRANT` to `app_user`" does not protect it: `sql/00_create_app_user.sql` leaves an `ALTER DEFAULT PRIVILEGES IN SCHEMA public ... GRANT ALL ON TABLES TO app_user`, so the table is born with an explicit `GRANT` to the role and `REVOKE ... FROM PUBLIC` does not undo it. The first version of the patch passed every isolation test and yet `app_user` could read the key and sign any tenant; it was discovered because the negative control checked it explicitly. The key now lives in its own schema (`tenant_security`). The `ALTER DEFAULT PRIVILEGES` is catalogued separately as `HYG-07`.
- **`HYG-07`**: the plan (§10, step 34) proposed "limiting the `ALTER DEFAULT PRIVILEGES` to the application's five tables", and that cannot be done: default privileges are defined per role, schema and object type, not per table name. The right patch was the entry's own: delete the line. Besides, deleting it from the bootstrap script is not enough: the existing database keeps the privilege in `pg_default_acl` until it is revoked.
- **`PERF-02`**: the three spare copies of the model cost ~102 MB of measured *physical footprint*, not the estimated 270–360 MB. The estimate that consolidating them shortened startup is confirmed: the API import goes from 16.6 s to 5.6 s.
- **`BUG-07`**: the entry's minimal patch no longer applied (`tenant_id` became `uuid.UUID`), and fixing the `TypeError` would not have made the suite pass: DeepEval's judge uses OpenAI by default, with no key, and the question has no answer in the corpus. Nor would it have protected any fix from this audit.

---


## 2. Findings Index

| ID | Sev. | Title | Main location | Block |
|---|:---:|---|---|:---:|
| `SEC-01` | 🔴 | JWT `SECRET_KEY` hardcoded and committed | `src/api/auth.py:8` | 1 |
| `SEC-02` | 🔴 | `tenant_id` interpolated unvalidated into `SET` | 9 places in `src/services/` | 1 |
| `SEC-03` | 🟠 | `WHERE` built by concatenation in GraphRAG | `src/services/graphrag.py:80` | 1 |
| `SEC-04` | 🟡 | Path traversal through `filename` on ingestion | `src/api/routers/ingest.py:23` | 1 |
| `BUG-01` | 🟠 | Cache poisoned with the progress prefix | `src/api/routers/chat.py:119` | 2 |
| `BUG-02` | 🟠 | The cache intercepts tool executions | `src/api/routers/chat.py:27,77` | 2 |
| `BUG-03` | 🟠 | The conversation history is discarded | `src/services/agent_graph/nodes.py:18` | 2 |
| `BUG-04` | 🟠 | Docker bootstrap broken by the order of the SQL scripts | `docker-compose.yml:9` | 2 |
| `BUG-05` | 🟡 | The self-correction loop corrects nothing | `src/services/agent_graph/graph.py:11` | 2 |
| `BUG-06` | 🟡 | `top_k_retrieve` / `top_k_rerank` are decorative | `src/models/requests.py:7` | 2 |
| `BUG-07` | 🟡 | The only test suite cannot run | `tests/test_rag.py:28` | 5 |
| `BUG-08` | 🟠 | Re-ranker cache in `/tmp`: the app stops starting when it is lost | `src/services/reranker.py:10` | 0 |
| `BUG-09` | 🟠 | `/chat/stream/` does not answer greetings, out-of-scope topics or tools | `src/api/routers/chat.py:102` | 2 |
| `PERF-01` | 🟠 | No connection pool: ~11 connections per query | 9 `asyncpg.connect()` | 3 |
| `PERF-02` | 🟠 | Four copies of the embedding model in RAM | 4 modules in `src/services/` | 3 |
| `PERF-03` | 🟡 | `model.encode` blocks the event loop during ingestion | `src/services/ingestion.py:72` | 3 |
| `PERF-04` | 🟡 | `max_tokens=300` truncates the evaluator | `src/services/evaluator.py:60` | 3 |
| `DOC-01` | 🟠 | Token-by-token streaming no longer exists | `src/services/extractor.py:56` | 4 |
| `DOC-02` | 🟠 | The paper claims Pydantic validations that do not exist | `src/services/evaluator.py:14` | 4 |
| `DOC-03` | 🟠 | `.env.example` does not allow the project to start | `.env.example` | 4 |
| `DOC-04` | 🟡 | `NetworkX` documented but never used | `README.md` | 4 |
| `DOC-05` | 🟡 | `ARCHITECTURE.md` frozen at Phase 1 | `ARCHITECTURE.md` | 4 |
| `DOC-06` | 🟡 | Chunking: 400 tokens in the code vs. 500 in the paper | `src/services/ingestion.py:48` | 4 |
| `DOC-07` | 🟡 | LLM model misquoted throughout the documentation | 7 calls + `README.md` | 4 |
| `DOC-08` | ⚪ | Python 3.12 (badge) vs. 3.14 (`requires-python`) | `pyproject.toml:3` | 4 |
| `HYG-01` | 🟡 | Undeclared direct dependencies | `pyproject.toml` | 5 |
| `HYG-02` | 🟡 | Dead code committed in the root | repo root | 5 |
| `HYG-03` | ⚪ | Incomplete `.gitignore` | `.gitignore` | 5 |
| `HYG-04` | ⚪ | Deprecated `datetime.utcnow()` | `src/api/auth.py:41,43` | 5 |
| `SEC-05` | 🟠 | `app_user` can rewrite its own tenant context | RLS policies in `sql/01_init.sql` | 3 |
| `SEC-06` | 🟡 | Error responses return the exception text | `src/api/routers/ingest.py:39` | 1 |
| `BUG-10` | 🟠 | The semantic cache ignores the history | `src/services/cache.py:17` | 2 |
| `HYG-05` | 🟡 | Three services create their Anthropic client before loading `.env` | `src/services/router.py:10` | 5 |
| `HYG-06` | ⚪ | The database does not restart with Docker | `docker-compose.yml` | 5 |
| `HYG-07` | 🟡 | `ALTER DEFAULT PRIVILEGES` hands `app_user` every future table in `public` | `sql/00_create_app_user.sql:5` (already deleted) | 5 |
| `HYG-08` | 🟠 | The database data lives in an anonymous volume | `docker-compose.yml` | 5 |
| `SEC-07` | 🟠 | `app_user` can divert the application's queries to its own tables without RLS | `sql/00_create_app_user.sql:2` | 1 |
| `HYG-09` | ⚪ | `onnxruntime` telemetry aborts the process on shutdown | `src/services/reranker.py:38` (through FlashRank) | 5 |
| `HYG-10` | 🟠 | `uv sync` picks Python 3.15 and the install fails | `pyproject.toml:4` | 5 |
| `BUG-12` | 🟠 | Concurrent first embeddings hang or crash the process | `src/services/embeddings.py:28` | 2 |

The last eleven rows came after the snapshot (five from 2026-09-14, `HYG-07` from 2026-09-15, `HYG-08` and `SEC-07` from 2026-09-16, `HYG-09` from 2026-09-17, `HYG-10` from 2026-11-09 and `BUG-12` from 2026-11-10) and are not part of the count in §1.

---

## 3. Verified System Inventory

The real state of each file, checked against the inventory in `PAPER_PLAN.md` §1.

### 3.1. API layer

| File | Lines | Status | Notes |
|---|:---:|:---:|---|
| `src/api/main.py` | 28 | ✅ | CORS with `allow_origins=["*"]` + `allow_credentials=True`; no `lifespan` (see `PERF-01`) |
| `src/api/auth.py` | 80 | ⚠️ | `SEC-01`, `SEC-02`, `HYG-04`. Mock users in the source |
| `src/api/routers/chat.py` | 132 | ⚠️ | `BUG-01`, `BUG-02`. Two endpoints: `/chat/` (synchronous) and `/chat/stream/` (SSE) |
| `src/api/routers/ingest.py` | 39 | ⚠️ | `SEC-04`. Extension validation is correct |
| `src/api/__init__.py` | 0 | ✅ | empty |
| `src/api/routers/__init__.py` | 0 | ✅ | empty |

### 3.2. LangGraph orchestration

| File | Lines | Status | Notes |
|---|:---:|:---:|---|
| `src/services/agent_graph/state.py` | 28 | ⚠️ | `AgentState` without a `history` field (`BUG-03`); `messages` declared with an `operator.add` reducer but never populated |
| `src/services/agent_graph/graph.py` | 51 | ⚠️ | `BUG-05`. Correct topology: 3 nodes, 2 conditional edges |
| `src/services/agent_graph/nodes.py` | 116 | ⚠️ | `BUG-03`, `BUG-06`. The 3 nodes are well separated |
| `src/services/agent_graph/__init__.py` | 0 | ✅ | empty |

**Verified topology** (`graph.py:20-51`):

```
                    ┌──────────────┐
     entry ────────▶│  supervisor  │
                    └──────┬───────┘
                           │ route_supervisor
              ┌────────────┴────────────┐
              │ final_answer present?   │
        yes ──┴── END          no ──────┴──▶┌────────────┐
                                            │ researcher │◀──┐
                                            └─────┬──────┘   │
                                                  │ (direct  │
                                                  │   edge)  │
                                            ┌─────▼──────┐   │
                                            │ generator  │   │
                                            └─────┬──────┘   │
                                                  │ route_reviewer
                                    needs_more_info ∧ iter<2 ┘
                                                  │
                                                 END
```

### 3.3. Services

| File | Lines | LLM | Postgres | Status | Notes |
|---|:---:|:---:|:---:|:---:|---|
| `src/services/router.py` | 81 | ✅ | — | ✅ | Well-built prompt; the `history` parameter never receives data (fixed, `BUG-03`) |
| `src/services/history.py` | 33 | — | — | ✅ | Added while fixing `BUG-03`: formats the history window for the router and the generator |
| `src/services/retriever.py` | 75 | — | ✅ | ⚠️ | `SEC-02`, `PERF-01`, `PERF-02`. RRF is correct |
| `src/services/reranker.py` | 46 | — | — | ⚠️ | `BUG-08`. Single `Ranker` instance; uses `asyncio.to_thread` correctly |
| `src/services/extractor.py` | 90 | ✅ | — | ⚠️ | `DOC-01`: `generate_answer_stream` (l. 56-90) is dead code (fixed: today it is the normal path) |
| `src/services/graphrag.py` | 99 | ✅ | ✅ | ⚠️ | `SEC-02`, `SEC-03`, `PERF-01` |
| `src/services/ingestion.py` | 267 | ✅ | ✅ | ⚠️ | `DOC-06`, `PERF-02`, `PERF-03`. Multimodal (MD/TXT/PDF/image) is correct |
| `src/services/cache.py` | 62 | — | ✅ | ⚠️ | `SEC-02`, `PERF-01`, `PERF-02` |
| `src/services/memory.py` | 97 | ✅ | ✅ | ⚠️ | `SEC-02`, `PERF-01`, `PERF-02` |
| `src/services/evaluator.py` | 87 | ✅ | ✅ | ⚠️ | `DOC-02`, `PERF-04`. The only module without `load_dotenv()` |
| `src/services/tools.py` | 48 | — | — | ⚠️ | Synchronous `requests` inside an `async` path; the 5 s timeout is correct |

**Note on `evaluator.py`.** It is the only service that does not call `load_dotenv()` (compare with `retriever.py:5-6`, `cache.py:9`, `memory.py:10`, `graphrag.py:10`, `ingestion.py:17`). It works today only because it is imported after modules that do call it and `os.environ` is already populated. It is an undeclared import-order dependency: if `evaluator.py` were imported first, `DB_DSN` would fall back to the default and `ANTHROPIC_API_KEY` would be `None`.

**Note on `tools.py`.** The three tools use `requests` (synchronous) and are called from `supervisor_node`, which is `async` (`nodes.py:40`: `tool_result = tool_func(**intent.tool_args)`). Each call to CoinGecko or GitHub blocks the event loop for up to 5 seconds. It is not catalogued as a separate finding because it shares its cause and fix with `PERF-03`.

### 3.4. Models and contracts

| File | Lines | Status | Notes |
|---|:---:|:---:|---|
| `src/models/structured.py` | 12 | ✅ | `confidence_score` **does** have `ge=0.0, le=1.0` (compare with `DOC-02`) |
| `src/models/search.py` | 11 | ✅ | `RerankedResult` inherits correctly from `SearchResult` |
| `src/models/requests.py` | 11 | ⚠️ | `BUG-06`: `top_k_*` ignored. `IngestRequest` (l. 10-11) is not used by any endpoint |

### 3.5. Data schema

| File | Tables | `ENABLE RLS` | `FORCE RLS` | `GRANT` | Status |
|---|---|:---:|:---:|:---:|:---:|
| `sql/01_init.sql` | `documents`, `semantic_cache`, `user_memory`, `rag_evaluations` | ✅ 4/4 | ❌ 0/4 | ❌ | ⚠️ |
| `sql/apply_rls.sql` | `documents` (migration) | ✅ | ❌ | ❌ | ✅ |
| `sql/apply_cache.sql` | `semantic_cache` | ✅ | ✅ | ⚠️ fails | ⚠️ |
| `sql/apply_memory.sql` | `user_memory` | ✅ | ✅ | ⚠️ fails | ⚠️ |
| `sql/apply_evaluator.sql` | `rag_evaluations` | ✅ | ✅ | ⚠️ fails | ⚠️ |
| `sql/apply_graphrag.sql` | `knowledge_graph` | ✅ | ✅ | ⚠️ fails | ⚠️ |
| `sql/create_app_user.sql` | — (creates the role) | — | ✅ only `documents` | ✅ | ⚠️ |

The `GRANT`s marked "fails" are those of `BUG-04`: they run before the `app_user` role exists.

**Coverage gap.** `sql/01_init.sql` (the script `PAPER_PLAN.md` §1 describes as the *"unified script"*) **does not create `knowledge_graph`** and **does not apply `FORCE ROW LEVEL SECURITY` to any table**. Without `FORCE`, the table owner bypasses its own RLS policies. If someone connects with the `.env.example` DSN (user `postgres`, which is the owner), multi-tenant isolation is not applied at all on the four tables of `01_init.sql`. See `DOC-03`.

### 3.6. Confirmed dead code

| File | Reason | Reference |
|---|---|---|
| `src/pipeline.py` (44 l.) | `retrieve_documents(query, top_k=5)` without `tenant_id` → `TypeError` | `HYG-02` |
| ~~`src/services/extractor.py:56-90`~~ | ~~`generate_answer_stream` never called~~ (brought back while fixing `DOC-01`) | `DOC-01` |
| `tests/test_rag.py` (broken) | the same `TypeError` at l. 28 | `BUG-07` |
| `src/models/requests.py:10-11` | `IngestRequest` never used (the endpoint uses `UploadFile`) | `HYG-02` |
| `src/services/ingestion.py:48` | `overlap` parameter declared and never read | `DOC-06` |
| `src/services/agent_graph/state.py:9` | `messages` declared, always `[]` | `BUG-03` |
| `test_chunk.py`, `test_db.py`, `test_sim.py`, `test_sse.py` | local validation scripts in the root | `HYG-02` |
| `scratch_db.py`, `scratch_stream.py` | experiments in the root | `HYG-02` |
| `uvicorn.log` (153 B) | committed log | `HYG-03` |

Verification:

```bash
grep -rn "generate_answer_stream\|IngestRequest\|networkx" src/ tests/
# only match: the definition in extractor.py:56 and requests.py:10
```

---

## 4. Security

### `SEC-01` 🔴 JWT `SECRET_KEY` hardcoded and committed

**Location.** `src/api/auth.py:8-10`

```python
SECRET_KEY = "super_secret_ai_sandbox_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
```

**Analysis.** HS256 is a **symmetric** algorithm: the same key signs and verifies. `create_access_token` (l. 38-46) signs with it and `get_current_user` (l. 72) verifies with it. Whoever knows the key can issue tokens indistinguishable from legitimate ones.

The key is in a public portfolio repository. It is not a secret.

**Full exploitation chain.**

1. Read `auth.py:8` → get `SECRET_KEY`.
2. Sign a token with an arbitrary `tenant_id`:
   ```python
   import jwt, datetime
   token = jwt.encode(
       {"sub": "attacker",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
       "super_secret_ai_sandbox_key", algorithm="HS256")
   ```
3. `get_current_user` (l. 72-80) accepts it without objection: it checks the signature and that `sub` and `tenant_id` are not null. Nothing else.
4. The `tenant_id` travels to `SET app.current_tenant` on the nine data paths. **RLS grants access legitimately**, because from its point of view the request is authorized.

**What is exposed.** The victim tenant's five tables: `documents` (the full content of the ingested files), `user_memory` (personal facts silently extracted in the background), `semantic_cache` (history of questions and answers), `rag_evaluations` (evaluated queries) and `knowledge_graph` (entity graph).

**Impact on the documentation.** It defeats the central argument of three documents: `README.md` §3 (*"Full isolation of customer data"*), `PAPER.md` §4.4 and `GRAPHRAG_ARCHITECTURE.md` §1. The RLS policies are correct and work; the problem is that the **entry** into the system can be forged.

**Aggravating factor.** The mock credentials are in the same source file (`auth.py:23-34`): `bryan` / `password123` and `company_x` / `password123`. There is no need to forge a token to get in as either tenant.

**Reproduction.**

```bash
grep -n "SECRET_KEY\|password" src/api/auth.py
# 8:  SECRET_KEY = "super_secret_ai_sandbox_key"
# 26:     "password": "password123",
# 32:     "password": "password123",
```

**Patch.**

```diff
--- a/src/api/auth.py
+++ b/src/api/auth.py
@@
+import os
+
-SECRET_KEY = "super_secret_ai_sandbox_key"
+# No default: the process must fail at startup if it is not set.
+SECRET_KEY = os.environ["JWT_SECRET_KEY"]
 ALGORITHM = "HS256"
```

Add to `.env.example` (see `DOC-03`):

```
# Generate with: openssl rand -hex 32
JWT_SECRET_KEY=change_this_to_a_random_32_byte_key
```

Mock users are acceptable in a declared sandbox, but an explicit comment saying that `FAKE_USERS_DB` is not an authentication system and that the passwords are not hashed is worth adding.

**Status: ✅ fixed (2026-09-11).** `SECRET_KEY` is now read from `JWT_SECRET_KEY` with no default: if it is missing, or shorter than 32 characters, the process does not start. A token signed with the old key returns 401. The comment on `FAKE_USERS_DB` was added too.

---

### `SEC-02` 🔴 `tenant_id` interpolated unvalidated into `SET app.current_tenant`

**Location.** Nine places, identical syntax:

| File:line | Function |
|---|---|
| `src/services/retriever.py:32` | `retrieve_documents` |
| `src/services/cache.py:23` | `check_semantic_cache` |
| `src/services/cache.py:51` | `save_semantic_cache` |
| `src/services/memory.py:50` | `extract_and_save_facts` |
| `src/services/memory.py:72` | `retrieve_user_facts` |
| `src/services/graphrag.py:53` | `insert_knowledge_graph` |
| `src/services/graphrag.py:67` | `retrieve_subgraph` |
| `src/services/evaluator.py:68` | `evaluate_rag_response` |
| `src/services/ingestion.py:186` | `insert_documents` |

```python
await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
```

**On the interpolation itself.** `SET` does not accept bound parameters in PostgreSQL's extended protocol, so building the statement as a string is technically unavoidable with asyncpg. **That is not the defect.**

**The defect** is that `tenant_id` travels unvalidated from the JWT payload to the SQL statement:

```
JWT payload (auth.py:74)  →  User.tenant_id: str (auth.py:20)
                          →  current_user.tenant_id (chat.py:27)
                          →  AgentState["tenant_id"] (chat.py:37)
                          →  f"SET app.current_tenant = '{tenant_id}'"
```

`User.tenant_id` is typed as `str` (`auth.py:20`), which accepts any string. Nowhere along that chain is it checked to be a UUID.

**Exploitation chain.** Chained with `SEC-01`, a token forged with

```python
"tenant_id": "x'; DROP TABLE documents CASCADE; --"
```

produces the statement:

```sql
SET app.current_tenant = 'x'; DROP TABLE documents CASCADE; --'
```

asyncpg's `conn.execute()` uses the simple protocol when there are no parameters, which **allows multiple statements separated by `;`**. It runs with the privileges of `app_user`, which `sql/create_app_user.sql:2-5` grants `ALL PRIVILEGES` on the whole database. The `ON DELETE CASCADE` of `knowledge_graph.source_chunk_id` (`apply_graphrag.sql:7`) spreads the destruction to the graph.

**Reproduction.**

```bash
grep -rn "SET app.current_tenant" src/ | wc -l   # 9
grep -n "tenant_id: str" src/api/auth.py          # 20: tenant_id: str
```

**Patch.** A single line at the edge closes the whole vector for the nine paths:

```diff
--- a/src/api/auth.py
+++ b/src/api/auth.py
@@
+import uuid
 from pydantic import BaseModel
@@
 class User(BaseModel):
     username: str
-    tenant_id: str
+    tenant_id: uuid.UUID   # Pydantic rejects anything that is not a valid UUID
```

With the type set to `uuid.UUID`, Pydantic validates when building `User` (l. 80) and `get_current_user` raises `ValidationError` before the value touches the data layer. The services then receive a `UUID` object, whose f-string representation is always the canonical form of 36 hexadecimal characters and hyphens, with no possible quotes.

If changing the public type is not desirable, the explicit alternative:

```python
try:
    uuid.UUID(tenant_id)
except (ValueError, TypeError, AttributeError):
    raise credentials_exception
```

**Recommended defense in depth.** Even with the edge validated, it is better to use the server's quoting function instead of direct interpolation:

```python
await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant_id))
```

`set_config()` is an ordinary SQL function and accepts bound parameters, removing the interpolation entirely at the nine places. It is the definitive fix.

**Status: ✅ fixed (2026-09-11).** `User.tenant_id` is now typed as `uuid.UUID`, so Pydantic rejects at the edge any value able to carry SQL: a malicious `tenant_id` in the token returns 401 instead of reaching the `SET`. The signatures of the nine downstream functions were updated to `uuid.UUID`, and `ingest.py` validates the `--tenant` argument with `type=uuid.UUID`. RLS isolation verified against the real database. The defense in depth with `set_config()` is still pending.

**Update (2026-09-15, with `PERF-01`).** The defense in depth is now applied. No query interpolates the tenant any more: `tenant_connection()` (`src/services/db.py`) sets it as a parameter with `set_config('app.current_tenant', $1, true)`, local to a transaction, and it is the only place in the code that does it. What remains open is that an injected statement can rewrite it (`SEC-05`), which a parameter does not prevent.

---

### `SEC-03` 🟠 `WHERE` built by concatenation in GraphRAG

**Location.** `src/services/graphrag.py:69-89`

```python
import re
words = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 3]
if not words:
    return ""

conditions = []
for word in words:
    conditions.append(f"source_node ILIKE '%{word}%' OR target_node ILIKE '%{word}%'")

sql_query = f"""
SELECT source_node, relation, target_node
FROM knowledge_graph
WHERE {' OR '.join(conditions)}
LIMIT 10
"""

rows = await conn.fetch(sql_query)
```

**Analysis.** Fragments derived from the **user's natural language query** (completely untrusted data) are interpolated directly into the `WHERE` clause.

**Current state: not exploitable.** `re.findall(r'\w+', query)` in Python 3 with Unicode strings captures `[a-zA-Z0-9_]` plus Unicode alphanumeric characters. The single quote (`'`) is not part of `\w`, so it never survives the filter. The injection is blocked.

**Why it is still a finding.** The safety of this query does not depend on the data access mechanism but on a regex eight lines above, with no comment explaining that responsibility. Plausible scenarios that break it:

- Allowing hyphens to capture entities like `multi-tenant` → `r'[\w-]+'` is still safe, but it is a blind change.
- Moving to phrase search instead of single words (a natural GraphRAG improvement) → introduces spaces and probably punctuation.
- Relaxing `len(w) > 3` or the pattern to support another language or alphabet.

Any of those changes reintroduces the injection without anything in the code flagging it.

**Secondary cost.** The construction is also inefficient: with 8 keywords it generates 16 `ILIKE` predicates with a leading wildcard (`'%word%'`), which **cannot use the B-tree indexes** `kg_source_idx` and `kg_target_idx` from `apply_graphrag.sql:10-11`. Every graph query is a full *sequential scan* of `knowledge_graph`.

**Reproduction.**

```bash
sed -n '69,89p' src/services/graphrag.py
```

**Patch.** A parameterized array with `ILIKE ANY`:

```diff
-        conditions = []
-        for word in words:
-            conditions.append(f"source_node ILIKE '%{word}%' OR target_node ILIKE '%{word}%'")
-
-        sql_query = f"""
-        SELECT source_node, relation, target_node
-        FROM knowledge_graph
-        WHERE {' OR '.join(conditions)}
-        LIMIT 10
-        """
-
-        rows = await conn.fetch(sql_query)
+        patterns = [f"%{w}%" for w in words]
+        sql_query = """
+        SELECT source_node, relation, target_node
+        FROM knowledge_graph
+        WHERE source_node ILIKE ANY($1::text[])
+           OR target_node ILIKE ANY($1::text[])
+        LIMIT 10
+        """
+        rows = await conn.fetch(sql_query, patterns)
```

Shorter, safe regardless of the regex, and with a stable execution plan (a single prepared statement instead of a different one for every combination of words).

To get index use back, the complementary improvement is a trigram index:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX kg_source_trgm_idx ON knowledge_graph USING GIN (source_node gin_trgm_ops);
CREATE INDEX kg_target_trgm_idx ON knowledge_graph USING GIN (target_node gin_trgm_ops);
```

**Status: ✅ fixed (2026-09-14).** The patch above was applied. The query words travel as a parameter and safety no longer depends on the regex. `%` and `_` inside a word still act as `ILIKE` wildcards, as before. Escaping them adds no safety, because a parameter cannot alter the SQL, and it would change results on real data: 13 triples in the database have nodes with `_` (`api_gateway`, `buenas_prácticas_de_desarrollo`…). The trigram index is not applied here: it is performance, not security, and it requires touching the SQL scripts, which is better done together with `BUG-04`.

Verified by running the old and the new version against real Postgres, connected as `app_user` (no `SUPERUSER` or `BYPASSRLS`, with `FORCE ROW LEVEL SECURITY`).

*Negative control.* The tokenizer was replaced by a permissive one, the scenario this finding anticipates:

| Payload | Before | After |
|---|---|---|
| Tautology (`…%' or true or source_node ilike '%…`) | 10 rows without matching any word | 0 rows |
| Legitimate apostrophe (`o'brien`) | `PostgresSyntaxError`: the researcher goes down | 0 rows |
| Cross-tenant read, as a tenant with no triples | **10 triples from the other tenant** | 0 rows |

**The third row corrects this finding's assessment.** It was assumed that an injection here would be contained by RLS. It is not. The payload adds a `UNION` whose `FROM` runs `set_config('app.current_tenant', '<other tenant>', false)` before scanning `knowledge_graph`, and the RLS policy evaluates `current_setting` row by row, so it already reads the rewritten tenant. `app_user` can change the variable its own isolation depends on. That is why **any** SQL injection in the system defeats multi-tenant isolation, not just this one. Catalogued as `SEC-05`.

*Equivalence.* With the real tokenizer, 16 queries over the data of the tenant with a graph: the same full set of matches without `LIMIT` (0 to 21 rows) and the same `retrieve_subgraph` output on all 16. Three more checks: the tenant with no triples sees nothing with any query, the real `researcher_node` prepends the subgraph (10 triples) to the context, and the database is left unchanged, because the test only reads.

---

### `SEC-04` 🟡 Path traversal through `filename` on ingestion

**Location.** `src/api/routers/ingest.py:15-27`

```python
ext = os.path.splitext(file.filename)[1].lower()
if ext not in ALLOWED_EXTENSIONS:
    raise HTTPException(status_code=400, detail=f"Extensión no permitida...")

temp_dir = tempfile.gettempdir()
temp_file_path = os.path.join(temp_dir, file.filename)

with open(temp_file_path, "wb") as buffer:
    shutil.copyfileobj(file.file, buffer)
```

**Analysis.** `file.filename` comes from the `Content-Disposition` header of the multipart request and is entirely controlled by the client. It is used unsanitized in `os.path.join`, which has the property of **resolving relative components**:

```python
os.path.join("/tmp", "../../home/user/.config/nvim/init.txt")
# → '/tmp/../../home/user/.config/nvim/init.txt'  → writes outside /tmp
```

**Existing partial mitigation.** The comment on line 10 (*"Allowed files, to avoid vulnerabilities"*) shows that the defensive intent is there, and the extension check (l. 18) limits the targets to `.md`, `.txt`, `.pdf`, `.png`, `.jpg`, `.jpeg`. That **reduces** the impact but does not remove it: it is still possible to overwrite any file with those extensions the process can write to. It requires prior authentication, which `SEC-01` makes trivial.

**Second defect in the same block: name collisions.** Since the path is derived from the original name, two users (from different tenants) uploading `cv.pdf` at the same time write over the same `/tmp/cv.pdf`. A concrete scenario:

1. Tenant A uploads `cv.pdf` → it is written to `/tmp/cv.pdf`, `ingest_file` starts.
2. Tenant B uploads its `cv.pdf` → it **overwrites** `/tmp/cv.pdf`.
3. A's `ingest_file`, still reading the file (`ingestion.py:218` or `process_pdf`), ingests B's document **under A's `tenant_id`**.
4. The `finally` on lines 37-38 deletes the file, and the second ingestion can fail because the file no longer exists.

It is a cross-tenant data leak through a race condition, independent of `SEC-01`.

**Reproduction.**

```bash
sed -n '20,27p' src/api/routers/ingest.py
```

**Patch.** `NamedTemporaryFile` solves both problems at once:

```diff
-    temp_dir = tempfile.gettempdir()
-    temp_file_path = os.path.join(temp_dir, file.filename)
-
     try:
-        with open(temp_file_path, "wb") as buffer:
+        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as buffer:
+            temp_file_path = buffer.name
             shutil.copyfileobj(file.file, buffer)
```

`NamedTemporaryFile` generates a random name inside the temporary directory (no traversal possible) that is unique (no collision). It requires moving the declaration of `temp_file_path` and initializing it to `None` before the `try` so the `finally` stays valid.

A minimal alternative if the original name is to be kept for traceability (the name is stored as `metadata["source"]` in `ingestion.py:195`):

```python
safe_name = os.path.basename(file.filename)
temp_file_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{safe_name}")
```

**Status: ✅ fixed (2026-09-14).** The file goes to disk with `NamedTemporaryFile` and `file.filename` no longer touches any path: it is reduced to its `basename` and travels as metadata through a new parameter, `ingest_file(..., source=...)`. The patch above, applied alone, would have changed `metadata["source"]` to the temporary file's random name, because `ingest_file` derived it from the disk path. For the same reason, the 22 rows of `documents` in the audited database store the server's full temporary path as their source (`/var/folders/…/T/bbobadilla_resume.pdf`).

**The impact was larger than described.** The `finally` deletes the file at the end, so the traversal does not just overwrite the target: it **removes** it.

Verified against a real uvicorn with the multipart built by hand, so that no client sanitizes the name (starlette 1.6 does not). `ingest_file` was replaced by a double that records the path and content it receives:

| Property | Before | After |
|---|:---:|:---:|
| The disk path stays inside the temporary directory | ❌ | ✅ |
| A victim file reached with `../` survives | ❌ deleted | ✅ |
| The visible name is the `basename`, without directories | ❌ | ✅ |
| Two tenants uploading `cv.txt` at once each ingest their own | ❌ tenant A ingested B's | ✅ |
| Both uploads end in 200 | ❌ B → 500 (A's `finally` deleted its file) | ✅ |
| Different temporary paths | ❌ | ✅ |
| Temporary files deleted after the request | ✅ | ✅ |

In the race, the double waits 0.5 s before reading so the window does not depend on the scheduler's luck. The race exists without that wait too.

Real ingestion (Claude and Postgres, no doubles) of a `.txt` and a `.png` uploaded as `../../intruso/<name>`: 8/8. `metadata.source` and the `[Image …]` label carry the original name, the rows land under the token's tenant and GraphRAG extracts their triples. The database was returned to its initial state.

Left out of this finding: the endpoint's `except` returns `detail=str(e)`, and in the race test that 500 handed the client the server's internal path. Catalogued as `SEC-06`.

---

### `SEC-05` 🟠 `app_user` can rewrite its own tenant context

> After the snapshot: found on 2026-09-14 while verifying `SEC-03`.

**Location.** The five RLS policies in `sql/01_init.sql`, which filter by `current_setting('app.current_tenant')`, and the `app_user` role from `sql/00_create_app_user.sql`, which the application connects as.

**Analysis.** Multi-tenant isolation depends on a session variable the application sets before each query. The same role that runs the queries can change it: `set_config()` is an ordinary SQL function, and PostgreSQL offers no way to stop a role from setting a custom variable (`app.*`). An injected statement can therefore rewrite the tenant mid-execution and read another tenant's data.

RLS thus stops being a second barrier: it only isolates as long as there is no SQL injection. That is the premise `SEC-03` took for granted, and it is false.

**Evidence.** Against real Postgres, connected as `app_user` (no `SUPERUSER` or `BYPASSRLS` and with `FORCE ROW LEVEL SECURITY`), the old version of `retrieve_subgraph` was run with a tokenizer that let quotes through. The connection was that of a tenant with no triples, and the injected word was:

```
zzqx%' or true union select source_node, relation, target_node from (select set_config('app.current_tenant', '11111111-1111-1111-1111-111111111111', false)) s, knowledge_graph --
```

It returned **10 triples from the other tenant**. The `FROM` of the second branch runs `set_config` before scanning `knowledge_graph`, and the policy evaluates `current_setting` row by row, so it already reads the rewritten tenant. With the fixed code, the same payload returns 0 rows.

**Why 🟠 and not 🔴.** Today there is no entry vector. `SEC-02` and `SEC-03` closed the two known injections, and the other queries use parameters. It is a missing defense in depth, not a vulnerability exploitable now; but it turns any future injection into a cross-tenant leak.

**Reproduction.** The statement equivalent to the one verified, as `app_user`:

```sql
SELECT set_config('app.current_tenant', '00000000-0000-0000-0000-000000000000', false);
SELECT count(*) FROM knowledge_graph;                  -- 0: the tenant has no triples
SELECT source_node, relation, target_node FROM knowledge_graph WHERE source_node ILIKE '%zzqx%' OR true
UNION SELECT source_node, relation, target_node
FROM (SELECT set_config('app.current_tenant', '11111111-1111-1111-1111-111111111111', false)) s, knowledge_graph
LIMIT 10;                                              -- rows from the other tenant
```

**Patch.** It requires a design decision; no single line fixes it.

1. **Signed context.** The application sets the tenant together with an HMAC signature. The policies call a `SECURITY DEFINER` function that verifies the signature with a key stored in a table `app_user` cannot read. An injection can change the tenant, but not sign it.
2. **One role per tenant.** The policies use `current_user`, and each role's credentials are out of SQL's reach. It requires one pool per role. A `SET ROLE` from a base role that is a member of all of them does not work, because it is also within reach of an injection.
3. **Zero dynamic SQL as a checked rule.** A test or linter that fails on interpolation in `execute`/`fetch`. It does not fix the design; it lowers the chance of a vector appearing.

It is best decided together with `PERF-01`: both change how each connection gets its tenant (transaction-local `set_config`).

**Status:** ✅ fixed on 2026-09-15 with **option 1, signed context** (the user's decision).

`tenant_connection()` (`src/services/db.py`) now sets two transaction-local variables: `app.current_tenant` and `app.tenant_signature`, the latter being the HMAC-SHA256 of the tenant with the `TENANT_SIGNING_KEY` key. The five policies stop reading `current_setting` and call `app_current_tenant()`, a `SECURITY DEFINER`, `STABLE` function owned by `postgres` with a fixed `search_path`, which returns the tenant only if the signature matches the key in `tenant_security.signing_key`. An injected statement can rewrite both variables, but cannot sign them: the function returns `NULL` and no row is visible.

Verification as `app_user` against the real DB, with the finding's payload:

| Case | Before | After |
|---|:---:|:---:|
| Legitimate context (tenant with 128 triples) | 128 | 128 |
| Tenant rewritten by injection (the payload above) | **10** | **0** |
| Unsigned context (what the old code sent) | 128 | 0 |
| Context with a made-up signature | — | 0 |
| `app_user` reads the signing key | — | `permission denied for schema tenant_security` |

Against the real API, with the same question and the cache purged between phases: with the right key, 4 sources and confidence 0.95; with a wrong key, 0 sources and *"No hay información disponible en el contexto proporcionado"* ("No information available in the provided context"). The signature is the only thing that changes between the two phases, so it is what holds up the isolation.

**Measured cost.** The worry was that the HMAC would be evaluated row by row. It is not: the plan puts the function in as an `Index Cond`, and `pg_stat_user_functions` counts **2 calls per query** both on a 25,000-row scan and on five queries in a row (10 calls). It is a constant cost, not proportional to the rows: on 50,000 seeded rows, 30 full scans go from 54 ms to 69–71 ms (~0.5 ms per query, measured twice alternating the policy to rule out ordering).

**Startup.** The key is shared by the application (`.env`) and the database (`sql/01_init.sql` seeds it through `\getenv`, and `sql/migrations/apply_tenant_signing.sql` does the same on an existing database). Without it nothing starts halfway: `docker compose` refuses to interpolate, the init script aborts with a readable message (and the container exits, as in `BUG-04`) and the API raises `RuntimeError` when importing `db.py`.

---

### `SEC-06` 🟡 Error responses return the exception text

> After the snapshot: found on 2026-09-14 while verifying `SEC-04` and `BUG-02`.

**Location.** Three places:

| File:line | Form |
|---|---|
| `src/api/routers/ingest.py:39` | `raise HTTPException(status_code=500, detail=str(e))` |
| `src/api/routers/chat.py:96` | `raise HTTPException(status_code=500, detail=str(e))` |
| `src/api/routers/chat.py:182` | `yield f"data: {json.dumps({'error': str(e)})}\n\n"` |

**Analysis.** Any internal exception reaches the client verbatim: server filesystem paths, Postgres messages or configuration details of the Anthropic SDK. It gives useful information for preparing an attack. It requires being authenticated.

**Evidence.**
- Verifying `SEC-04`, the `/ingest/` 500 returned `{"detail": "/var/folders/v2/n7jcjy_11cscqrgkctpn931c0000gn/T/cv.txt"}`.
- Verifying `BUG-02`, with the Anthropic client without a key, `/chat/stream/` delivered *"Could not resolve authentication method. Expected either api_key or auth_token to be set…"* in the error event.

**Reproduction.**

```bash
grep -rn "str(e)" src/api      # ingest.py:39, chat.py:96, chat.py:182
```

**Patch.** Log the exception on the server and return a generic message with an identifier to correlate it:

```python
except Exception:
    error_id = uuid.uuid4().hex[:8]
    logger.exception("POST /ingest/ failed [%s]", error_id)
    raise HTTPException(status_code=500, detail=f"Internal error ({error_id})")
```

The `HTTPException`s with 400 or 422 are messages meant for the client and stay as they are. In `chat_endpoint`, the `except Exception` also catches and rewraps the `HTTPException` the block itself raises when the graph returns no answer. It is better to let `HTTPException` through before the generic case.

**Status:** ✅ fixed on 2026-09-15.

The three points log the exception with `logger.exception` (the project did not use `logging` anywhere; it is its first use, and it lives alongside the `print`s in the rest of the code) and return `Internal error (<id>)` to the client, with eight hexadecimal characters. The `error` key of the SSE event is kept, because it is the one `src/frontend/app.py:112` renders, as is `detail` for line 53.

Verification against a real server, forcing real failures (an invalid Anthropic key and a corrupt PDF):

| Point | What the client got before | After |
|---|---|---|
| `POST /chat/` | `Error code: 401 - {'type': 'error', ... 'message': 'API key is invalid.'}` | `Internal error (a85a8af2)` |
| `POST /chat/stream/` | the same 401, inside an HTTP 200 | `Internal error (e1942c67)` |
| `POST /ingest/` | `Failed to open file '/var/folders/v2/n7jcjy_.../tmp_f3a0h9w.pdf' as type pdf.` | `Internal error (81fa55bd)` |

Each of the three identifiers appears exactly once in the server log, next to its full traceback (`ERROR:src.api.routers.chat:POST /chat/ failed [a85a8af2]`), and the temporary file's path now exists only there. `grep -rn "str(e)" src/api` returns nothing.

What must not change, checked separately: the 400 for a disallowed extension arrives whole (`File type not allowed. Supported: {...}`), and the router's own 500 keeps its message (`The agent graph did not return a final answer.`) thanks to the `except HTTPException: raise` that now comes before the generic one. This second case lives entirely in the router, so it was triggered by replacing the graph with a double that returns a state without `final_answer`.

### `SEC-07` 🟠 `app_user` can divert the application's queries to its own tables without RLS

> After the snapshot: found on 2026-09-16 while fixing `HYG-07`.

**Location.** `sql/00_create_app_user.sql:2`, `GRANT ALL PRIVILEGES ON DATABASE postgres TO app_user`, plus the application's SQL, which names the tables without a schema (`FROM user_memory`, `INSERT INTO documents`…) in `src/services/`.

**Analysis.** `GRANT ALL` on the database grants three privileges: `CONNECT`, `TEMPORARY` and `CREATE`. `PUBLIC` already has the first two by default. `CREATE` is the only one it adds, and it allows creating schemas; the application does not need it, because it creates no objects at runtime. Inside a schema of its own, `app_user` owns what it creates: tables without RLS and even trusted extensions (`pg_trgm`, `hstore`…).

On its own, it would be excess privilege. What makes it serious is that it combines with something PostgreSQL does not allow preventing: **an ordinary role can set its own defaults** with `ALTER ROLE app_user SET ...`. If it sets `search_path = sombra, public`, every connection opened afterwards resolves unqualified tables first in `sombra`. asyncpg's `RESET ALL` when returning a connection to the pool does not prevent it, because it restores the role's default, which is precisely the one that was changed.

From then on, what the application writes goes to the attacker's tables, without RLS and readable without a signature, and what it reads comes from them. **The signed context of `SEC-05` protects nothing**: the policies are still intact on `public`, but the application no longer queries those tables. And the effect persists: it affects every request of every tenant until a superuser notices.

**Evidence.** A disposable database from a clean clone of `develop` (with `HYG-07` already fixed). The victim is tenant `2222…` and uses the real code: `tenant_connection()` with the statement from `memory.extract_and_save_facts` to write, and `memory.retrieve_user_facts()` to read, each step in a new process. The attacker is `app_user` connected directly, without a signature, which is what an injected statement or someone who knew the password would have.

| Step | Current privileges | With `REVOKE CREATE ON DATABASE` |
|---|---|---|
| Victim stores *"The user works with Kotlin"* | in `public` | in `public` |
| Attacker: `CREATE SCHEMA sombra` + `sombra.user_memory` with a planted fact | ok | `permission denied for database postgres` |
| Attacker: `ALTER ROLE app_user SET search_path = sombra, public` | ok | ok |
| `search_path` of the victim's next connection | `sombra, public` | `sombra, public` |
| Victim stores *"The office Wi-Fi password is Faro-2291"* | **goes to `sombra`** | in `public` |
| What the victim gets in their profile | **the planted fact** (*"authorizes payments to account ZX-4471 without confirmation"*) and the password; *Kotlin* is gone | *Kotlin* and the password |
| The attacker, without a signature, reads `public.user_memory` | 0 rows | 0 rows |
| The attacker, without a signature, reads `sombra.user_memory` | **the victim's two rows**, password included | the table does not exist |

Against the development database only privilege checks inside rolled-back transactions were done: `app_user` has `CREATE` (`datacl`: `app_user=CTc/postgres`), can create a schema, a table and the `pg_trgm` extension, and can run `ALTER ROLE app_user SET search_path`. It cannot create anything in `public` or in `tenant_security`. At the end, `pg_db_role_setting` is empty, there are no schemas owned by `app_user` and the counts are still 22 / 128 / 4 / 3 / 0.

**Residue that `REVOKE CREATE` does not close.** `ALTER ROLE` on itself is still available for any session parameter. Measured on the same database, already without `CREATE`: `ALTER ROLE app_user SET default_transaction_read_only = on` makes the application's next write fail with `ReadOnlySQLTransactionError`. It leaks no data, but it leaves the application unable to write, persistently. With `statement_timeout` the same would happen to every query (not measured).

**Why 🟠 and not 🔴.** For the same reason as `SEC-05`: it requires running arbitrary SQL as `app_user`, and today no injection is known. But it is worse than `SEC-05` in two ways: it survives the request that triggers it and it defeats the signed context. Besides, in this environment there is a path without injection: the `apppassword` password is committed and Compose publishes the port on all interfaces (`0.0.0.0:5433` and `[::]:5433`). Whoever reaches that port has the full precondition.

**Reproduction.** As `app_user`, in a disposable database (the `ALTER ROLE` is not session-local):

```sql
CREATE SCHEMA sombra;
CREATE TABLE sombra.user_memory (LIKE public.user_memory INCLUDING ALL);
ALTER ROLE app_user SET search_path = sombra, public;
-- In a new application connection: SHOW search_path  ->  sombra, public
-- Cleanup, as postgres: DROP SCHEMA sombra CASCADE; ALTER ROLE app_user RESET ALL;
```

**Patch.** In layers; only the first one is measured.

1. **Remove `CREATE` (measured).** In `00_create_app_user.sql`, `GRANT CONNECT ON DATABASE postgres TO app_user` instead of `GRANT ALL`, and a migration with `REVOKE CREATE ON DATABASE postgres FROM app_user` for the existing database. It closes the capture and the poisoning in the table above.
2. **Neutralize `search_path` in the application (not measured).** Qualify the tables (`public.documents`) in the SQL in `src/services/`, or pin the sensitive parameters when opening each connection (asyncpg's `server_settings`). It remains to be checked that a value set on connecting survives the pool's `RESET ALL`.
3. **Watch the residue (not measured).** `pg_db_role_setting` must be empty for `app_user`. A healthcheck or a startup test that checks it detects both the diversion and the `default_transaction_read_only`.

Not measured, and outside this finding: `TEMPORARY`, which `PUBLIC` has, allows shadowing within a single session with a temporary table, because `pg_temp` is searched before `public`. Going by asyncpg 0.31's code, the pool does not run `DISCARD TEMP` when recycling connections (`get_reset_query()`: `pg_advisory_unlock_all`, `CLOSE ALL`, `UNLISTEN *`, `RESET ALL`), so the temporary table would survive as long as the connection lives. Layer 2 would cover it too.

**Status:** 🟡 **layer 1 fixed** on 2026-09-16. Layers 2 and 3 remain open, to be decided together with `BUG-07`.

**Changes.** `sql/00_create_app_user.sql` grants `GRANT CONNECT` instead of `GRANT ALL`. `sql/migrations/apply_revoke_database_create.sql` runs `REVOKE ALL` + `GRANT CONNECT` on an existing database, so it ends up identical to a new one. `TEMPORARY` still comes through `PUBLIC`. The migration does not undo a diversion already in place, so its header carries the two queries to check first.

**Verification.** Two disposable databases from a clean clone, with the same attack as in the evidence and the application's real code:

| | `HEAD` (`GRANT ALL`) | With the patch |
|---|---|---|
| `app_user`'s `datacl` | `CTc` | `c` |
| `CREATE SCHEMA sombra` | ok | `permission denied for database postgres` |
| The victim's write after the `ALTER ROLE` | to `sombra` | to `public` |
| Profile the victim gets | planted fact + password | *Kotlin* + password, their own |
| The attacker, without a signature, reads the password | yes | no (`UndefinedTableError`) |
| Signed `app_user`: insert, update, read and delete on the five tables | 1/1/1/1/1 | 1/1/1/1/1 |

`pg_dump --schema-only` and the role definition differ only in the random `\restrict` tokens and the password salt (the database ACL is not part of the schema dump).

**Development database.** Before migrating it was checked that there was no diversion already: `pg_db_role_setting` empty and no schema owned by `app_user`. After the migration, `datacl` is the same as in a new database (`app_user=c/postgres`) and `CREATE SCHEMA` gives permission denied. As signed `app_user`, it still reads the 128 triples and writes to `user_memory` (in a rolled-back transaction). Counts, 22 / 128 / 4 / 3 / 0 before and after. The full API was not run: the application runs no DDL and the real data path was checked on the disposable database.

**Still open.** The residue of `ALTER ROLE` on itself (measured: `default_transaction_read_only` blocks writes) and, with it, that a `search_path` pointing at a schema `app_user` cannot create stops being harmless if it ever gets `CREATE` back. It is the decision between layers 2 and 3.

---

## 5. Functional Defects

### `BUG-01` 🟠 Cache poisoned with the progress prefix

**Location.** `src/api/routers/chat.py:100-123`

**Analysis.** The SSE generator accumulates each node's progress messages in a single text variable:

```python
accumulated_answer = ""
...
    if node_name == "supervisor":
        accumulated_answer += "🤖 *Supervisor evaluando estrategia...*\n\n"
    elif node_name == "researcher":
        accumulated_answer += "🔍 *Investigador buscando en Postgres Vector y GraphRAG...*\n\n"
    elif node_name == "generator":
        accumulated_answer += "✍️ *Redactor estructurando respuesta final...*\n\n---\n\n"
```

When the real answer arrives, it **concatenates it onto the accumulated text** and stores that same dictionary:

```python
final_dict = state_update["final_answer"].model_dump()
final_dict["answer"] = accumulated_answer + (final_dict.get("answer") or "")   # ← l. 119
yield f"data: {json.dumps(final_dict)}\n\n"
...
if final_dict:
    await save_semantic_cache(current_user.tenant_id, request.query, final_dict)   # ← l. 123
```

The purpose of the concatenation is right for the stream (the frontend computes character diffs in `app.py:119-122`, so the answer must arrive as a continuation of the text already emitted). The mistake is **reusing that object for storage**.

**Actual content of a cache row.**

```
🤖 *Supervisor evaluando estrategia...*

🔍 *Investigador buscando en Postgres Vector y GraphRAG...*

✍️ *Redactor estructurando respuesta final...*

---

Bryan tiene experiencia en arquitecturas cloud sobre AWS...
```

**Cumulative degradation.** On the next hit, `chat.py:79` prepends another marker:

```python
cached_data["answer"] = "⚡ [CACHE HIT] " + cached_data.get("answer", "")
```

resulting in `⚡ [CACHE HIT] 🤖 *Supervisor evaluando…* 🔍 *Investigador…* ✍️ *Redactor…* --- <answer>`. The user sees an execution trace **that did not happen** (the graph did not run, it was a cache hit) describing steps the system skipped.

**Side effect on the evaluator.** Line 127 passes `final_dict.get("answer", "")`, already polluted, to `evaluate_rag_response`. The LLM judge evaluates *faithfulness* on a text that starts with three lines of UI metadata absent from the retrieved context. It is systematic noise that biases downwards the metric `README.md` §4 presents as active observability.

**Asymmetry between endpoints.** The synchronous `/chat/` endpoint (l. 56) correctly caches `structured_response.model_dump()` without pollution. Only the SSE endpoint (the one the frontend uses) is affected. That explains why the defect went unnoticed if the tests were done against `/chat/`.

**Reproduction.**

```bash
sed -n '112,124p' src/api/routers/chat.py
```

On an existing database, to measure the extent:

```sql
SELECT count(*) FROM semantic_cache WHERE response_json->>'answer' LIKE '%Supervisor evaluando%';
```

**Patch.** Separate the object that is emitted from the one that is stored:

```diff
                         if "final_answer" in state_update and state_update["final_answer"]:
-                            final_dict = state_update["final_answer"].model_dump()
-                            # Anexamos la respuesta final real
-                            final_dict["answer"] = accumulated_answer + (final_dict.get("answer") or "")
-                            yield f"data: {json.dumps(final_dict)}\n\n"
+                            # Clean object: the one that is cached and evaluated.
+                            final_dict = state_update["final_answer"].model_dump()
+                            # Object for the stream: it continues the text already emitted to the client.
+                            stream_dict = {
+                                **final_dict,
+                                "answer": accumulated_answer + (final_dict.get("answer") or ""),
+                            }
+                            yield f"data: {json.dumps(stream_dict)}\n\n"
```

With that, `save_semantic_cache` (l. 123) and `evaluate_rag_response` (l. 127) get the clean object with no further changes.

**Cleanup of existing data.** A prerequisite: the fix stops new polluted rows from being generated, but the existing ones are still served. The pattern is best anchored to the **start** of the string (the pollution is always a prefix) so as not to delete a legitimate answer that mentions the Supervisor in the middle of the text:

```sql
DELETE FROM semantic_cache
WHERE response_json->>'answer' LIKE '🤖 *Supervisor evaluando estrategia...*%';
```

It must run as `postgres`: under RLS, `app_user` only sees one tenant's rows per session.

**Status: ✅ fixed (2026-09-11).** `stream_dict` (with progress, for SSE) separated from `final_dict` (clean, for the cache and the evaluator). Verified end to end with the graph mocked: the last SSE event keeps the progress prefix (the frontend still renders the diffs correctly), while the stored object and the text sent to the judge start with the real answer, with `confidence_score` and `sources` intact.

**Damage found in the audited database:** 4 of 8 `semantic_cache` rows polluted (50%), all coming from the SSE endpoint; the 4 clean ones came from the synchronous endpoint. Purged with the anchored query above.

---

### `BUG-02` 🟠 The cache intercepts tool executions

**Location.** `src/api/routers/chat.py:26-29` (synchronous) and `:77-81` (SSE)

```python
cached_data = await check_semantic_cache(current_user.tenant_id, request.query)
if cached_data:
    return StructuredAnswer(**cached_data)
```

**Analysis.** The cache is checked **before** the supervisor classifies the intent, and storing (l. 56 and l. 123) does not check the resulting `intent_type` either. Every answer is cached alike, deterministic or not.

**A clarification on scope (verified while fixing `BUG-01`).** The two endpoints do not behave the same:

- **`/chat/` (synchronous, l. 56)** caches unconditionally, including `tool_execution` answers. Here the defect shows up in full.
- **`/chat/stream/` (SSE, l. 123)** only assigns `final_dict` inside the `elif node_name == "generator"` branch. When the supervisor resolves on its own (greeting, tool, `out_of_scope`), `route_supervisor` goes straight to `END`, the generator node never runs and `final_dict` stays `None`: **nothing is stored**.

Since the frontend uses the SSE endpoint, in practice tool results are not being cached today (the audited database confirms it, with not a single tool row). But the defect is still real in two ways: `/chat/` does store them, and **reading** the cache (l. 27 and l. 77) happens on both endpoints, so a row stored through `/chat/` is later served to stream users. The fix below covers both paths.

The problem is that three of the four intents produce answers that are **inherently not cacheable**:

| Intent | Cacheable | Reason |
|---|:---:|---|
| `knowledge_search` | ✅ | Deterministic as long as the corpus does not change |
| `casual_greeting` | ✅ | Harmless |
| `tool_execution` | ❌ | The value changes on every call, by definition |
| `out_of_scope` | ⚠️ | Harmless, but it wastes index space |

**A concrete scenario.** With a similarity threshold of 0.85 (`cache.py:16`):

1. `10:00` — User: *"¿Qué hora es?"* ("What time is it?") → `tool_execution` → `get_current_time()` → *"La fecha y hora actual es: 2026-09-10 10:00:00"*. It is cached.
2. `14:30` — User: *"¿me dices la hora?"* ("can you tell me the time?") → similarity ≈ 0.88, above 0.85 → **cache hit** → *"⚡ [CACHE HIT] … 10:00:00"*.
3. The next day, and indefinitely: the same answer. The `semantic_cache` table has no expiry policy (`ROADMAP_PHASE_5_SCALABILITY.md` §3 correctly identifies it as future work), so the entry lives forever.

The same with `get_crypto_price` (a frozen Bitcoin price served as current) and `get_github_profile` (an outdated repo and follower count).

**Impact on the documentation.** `README.md` §1 presents the tools as *"External tools (function calling): the supervisor can divert the query to call external APIs deterministically"*. `PAPER.md` §6.5 and `PAPER_PLAN.md` §2 document all three. None of the three works correctly more than once.

**Reproduction.**

```bash
grep -n "check_semantic_cache\|save_semantic_cache\|intent_type" src/api/routers/chat.py
# 27, 56, 77, 123 → no reference to intent_type
```

**Patch.** Make storing conditional on the final state's `intent_type`. Synchronous endpoint:

```diff
+NON_CACHEABLE_INTENTS = {"tool_execution", "out_of_scope"}
+
@@
-        await save_semantic_cache(current_user.tenant_id, request.query, structured_response.model_dump())
+        if (final_state.get("intent_type") not in NON_CACHEABLE_INTENTS
+                and not structured_response.requires_more_info
+                and structured_response.confidence_score >= 0.5):
+            await save_semantic_cache(current_user.tenant_id, request.query, structured_response.model_dump())
```

SSE endpoint: capture `intent_type` from the supervisor's `state_update` (which is already iterated over at l. 104) and apply the same condition before l. 123.

The two extra conditions avoid another latent problem: today an answer with `requires_more_info=True` or `confidence_score=0.2` is cached all the same, that is, an answer the system itself considers insufficient is fixed forever.

**Status: ✅ fixed (2026-09-14).** Both endpoints store in the cache only if `is_cacheable(intent_type, answer)` allows it: the intent is in the allowlist `{knowledge_search, casual_greeting}`, `requires_more_info` is false and `confidence_score ≥ 0.5`. The stream takes `intent_type` from the supervisor's `state_update`. Three differences from the patch above:

- **An allowlist instead of a denylist.** `QueryIntent.intent_type` is a free `str` the LLM fills in, and with a denylist any unexpected value would be cached.
- **The scope changed.** The clarification above no longer holds: when `BUG-09` was fixed (2026-09-13), `/chat/stream/` started collecting the supervisor's answer too, and from then on it cached tools and `out_of_scope` just like `/chat/`.
- **The damage was greater.** It was not limited to stale data: it served **another query's** data. Measured with the real model (`all-MiniLM-L6-v2`, threshold 0.85):

| Query pair | Similarity | Hit? |
|---|:---:|:---:|
| `¿Cuánto vale bitcoin?` ↔ `¿Cuánto vale ethereum?` (how much is bitcoin / ethereum) | 0.886 | yes |
| `¿Cuál es la capital de Francia?` ↔ `¿Cuál es la capital de Chile?` (capital of France / Chile) | 0.860 | yes |
| `¿Qué hora es?` ↔ `¿me dices la hora?` (what time is it / can you tell me the time) | 0.815 | no |
| `Hola` ↔ `Hola, ¿qué hora es?` (hello / hello, what time is it) | 0.535 | no |

Greetings do not collide with requests that start with "Hola" (0.28–0.67 in the pairs measured), and that is why they stay cacheable.

Verified against a real uvicorn, with the real graph, LLM and Postgres, as the tenant with no rows in the cache. `analyze_query` was wrapped only to record the intent, without altering the result. The oracle: a graph answer writes a row in `semantic_cache` if and only if the policy allows it.

| Scenario | Before | After |
|---|---|---|
| `¿Qué hora es?` twice, `/chat/` | Hit: `12:58:15` both times | `13:00:58` → `13:01:02`, no row |
| `¿Qué hora es?` twice, `/chat/stream/` | Hit: `12:58:19` both times | `13:01:03` → `13:01:07`, no row |
| Bitcoin, then ethereum | Hit: *"El precio actual de Bitcoin es $78593 USD"* | *"El precio actual de Ethereum es $2507.41 USD"* |
| France, then Chile (`out_of_scope`) | Hit with France's answer | Its own answer, no row |
| Greeting | Cached | Cached |
| Repeated knowledge question (positive control) | Hit | Hit |
| Rows written against the policy | 4 | 0 (10 answers evaluated) |
| **Checks** | **3/8** | **8/8** |

Separately, 11 `is_cacheable` edge cases the LLM does not produce at will: `requires_more_info=True`, confidence 0.49 / 0.5 / `None`, an intent with other capitalization, empty or `None`. All correct. The database was returned to its initial state, after waiting for the background tasks to finish.

**Pending.** One row in the audited database would not pass the policy (`requires_more_info=true`, confidence 0.75) and is still being served: it is data decision D-02 in the remediation table. The cache does not take the history into account either, because the text of a follow-up question (*"¿Y en qué años?"*, "And in which years?") is not enough as a key: catalogued as `BUG-10`.

---

### `BUG-03` 🟠 The conversation history is discarded

**Location.** `src/services/agent_graph/nodes.py:18`

```python
intent = await analyze_query(state["query"], [])
```

**Analysis.** The history's chain of custody breaks at the last link. The full path:

| Step | Location | Status |
|---|---|:---:|
| The frontend builds the history | `src/frontend/app.py:87` | ✅ |
| It sends it in the payload | `src/frontend/app.py:88` | ✅ |
| `ChatRequest` declares and validates it | `src/models/requests.py:6` | ✅ |
| The endpoint receives `request.history` | `chat.py:24`, `:70` | ✅ |
| It is copied into `AgentState` | — | ❌ **broken** |
| `supervisor_node` passes it to `analyze_query` | `nodes.py:18` | ❌ receives `[]` |

`AgentState` (`state.py:7-28`) has no `history` field. Its `messages` field (declared with an `operator.add` reducer for accumulation, l. 9) is initialized as `[]` in `chat.py:36` and `:86` and **is never written**: no node returns `messages` in its return dictionary.

**What code is left unreachable.** `analyze_query` implements the full history formatting (`router.py:40-46`):

```python
history_str = ""
if history:
    recent_history = history[-4:]      # ventana de 4 mensajes para acotar tokens
    history_str = "Historial reciente de la conversación:\n"
    for msg in recent_history:
        history_str += f"- {msg['role'].upper()}: {msg['content']}\n"
```

With `history=[]`, `history_str` stays empty and is interpolated as an empty string into the prompt (l. 54). And the prompt's instruction (`router.py:68`):

> *"Si la pregunta depende de historial (ej: '¿Y qué hizo ahí?'), resuelve la correferencia en todas las variaciones."* ("If the question depends on the history (e.g. 'And what did he do there?'), resolve the coreference in every variation.")

has no data to work on.

**Functional impact.** Every follow-up question is handled as if it were the first of the conversation:

- *"¿Qué experiencia tiene Bryan en AWS?"* ("What experience does Bryan have with AWS?") → works.
- *"¿Y en qué años?"* ("And in which years?") → the supervisor does not know what "and in which years" refers to. In the best case it generates generic Multi-Query variants and retrieves irrelevant context; in the worst it classifies it as `out_of_scope`.

The *"¿Y qué hizo ahí?"* case the prompt uses as its canonical example is precisely the one that fails.

**Impact on the documentation.** `PAPER.md` §4.3.1 describes the supervisor resolving coreferences as an active capability. The docstring of `analyze_query` (`router.py:38`) says: *"Router agent: analyzes the user's intent and resolves coreferences using the history"*.

**Reproduction.**

```bash
grep -rn "history" src/ | grep -v "^src/frontend"
# src/models/requests.py:6  → declared
# src/services/router.py:36,40-46 → consumed
# no line connects the two
```

**Patch.** Three small changes.

1. `src/services/agent_graph/state.py`:

```diff
 class AgentState(TypedDict):
     messages: Annotated[Sequence[BaseMessage], operator.add]
     tenant_id: str
     user_profile: str
     query: str
+    history: List[Dict[str, str]]
```

2. `src/api/routers/chat.py`, in both `initial_state` (l. 35 and l. 85):

```diff
             query=request.query,
+            history=request.history,
             intent_type="",
```

3. `src/services/agent_graph/nodes.py:18`:

```diff
-    intent = await analyze_query(state["query"], [])
+    intent = await analyze_query(state["query"], state.get("history", []))
```

The 4-message window in `router.py:41` already bounds the token cost, so no further control is needed.

**Status: ✅ fixed (2026-09-11).** The three changes applied, plus a hardening of `analyze_query`: the client sends the history, so a turn without `role`/`content` (or one that is not a dictionary) is dropped instead of taking down the request with a `KeyError`.

Verified in five phases, with the *with history* / *without history* contrast as the control:

| Phase | What it checks | Result |
|:---:|---|---|
| 1 | The history is interpolated into the router's prompt; the window trims to the last 4 turns; without history no empty block is injected | ✅ |
| 2 | Malformed payload (turn without `role`, without `content`, not a dict, empty `content`, `None`): no exception, and the valid turn in a mix survives | ✅ |
| 3 | Chain of custody `AgentState` → `supervisor_node` → `analyze_query`: it receives the 2 turns intact; a state without the key degrades to `[]` without `KeyError` | ✅ |
| 4 | Real coreference against the API: *"¿Y en qué años?"* after talking about Betterfly → all 3 Multi-Query variations mention Betterfly. Without history → 3 generic variations about the whole timeline | ✅ |
| 5 | HTTP end to end (`POST /auth/token` → `POST /chat/` and `/chat/stream`) against the real graph and DB, spying on `retrieve_documents` | ✅ |

Phase 5 measures at the real boundary of the search (what text is queried against Postgres) because that is where the effect shows:

```
WITH history (4/4 queries resolve the coreference):
  · ¿En qué años trabajó Bryan Bobadilla en Betterfly?
  · Período de empleo años Betterfly Bryan Bobadilla
  · Fechas de trabajo experiencia Betterfly ingeniero
  · [HyDE] Bryan Bobadilla se desempeñó como Ingeniero de Software Senior Back End en Betterfly…

WITHOUT history (0/4), same literal question:
  · ¿En qué años trabajó Bryan Bobadilla en sus experiencias profesionales?
  · Años de experiencia y timeline laboral de Bryan Bobadilla
  · ¿Cuál es el periodo temporal o rango de años de las posiciones de Bryan Bobadilla?
  · [HyDE] Bryan Bobadilla ha tenido una trayectoria profesional que abarca desde 2015 hasta 2023…
```

Both endpoints are covered: `/chat/` and `/chat/stream` pass the history along alike. The semantic cache had to be purged between phases, because otherwise the second question is a *cache hit* of the first and the negative control stops being valid (a direct consequence of `BUG-02`). The database was left in its initial state (4 `semantic_cache` rows, 3 `user_memory`, 0 `rag_evaluations`).

**Follow-up, already closed: the generator did not see the history either.** The fix above reconnects the history to the **supervisor**, which is where the defect was located, and with that retrieval becomes correct. But verifying it showed that `generator_node` (`nodes.py:105`) called `generate_answer(query=state["query"], …)` with the raw question, so the generator got the right context without knowing what *"and"* referred to, and answered by listing the résumé's whole timeline (the same 11 years with and without history) instead of sticking to the Betterfly period. Retrieving the right thing was solved; writing about the right referent was not.

It was closed by passing `history` to `generate_answer` too, with an explicit instruction in its prompt to resolve the coreference and not dump the leftover context. Along the way, the history formatting (4-turn window and dropping malformed turns) was extracted to `src/services/history.py`, because the router and the generator must apply exactly the same rules, and keeping them duplicated is how they drift apart again.

The effect on the final answer, same literal question:

| | Answer to *"¿Y en qué años?"* | Years cited |
|---|---|:---:|
| Before | Dump of the résumé's whole timeline (1,039–1,202 characters) | 11 |
| After, **with** history | *"Bryan trabajó en Betterfly como Ingeniero de Software Senior – Back End desde **Abril 2024 hasta el presente**."* ("Bryan has worked at Betterfly as a Senior Software Engineer – Back End **from April 2024 to the present**.", 111 characters) | 1 |
| After, **without** history (control) | *"No puedo responder… es una pregunta de seguimiento que depende de una pregunta previa… Por favor, clarifica cuál es el tema."* ("I can't answer… it is a follow-up question that depends on a previous one… Please clarify the topic.") | 0 |

The control improves twice over: without history the system no longer makes up a plausible answer by dumping everything it retrieved, but says the referent is missing and asks for clarification. The 13 retrieval and generation checks pass in both runs, and the database returns to its initial state in both.

`generate_answer_stream` (`extractor.py:56`) was not touched: it has been dead code since the migration to LangGraph and its fate is decided in `DOC-01`.

---

### `BUG-04` 🟠 Docker bootstrap broken by the order of the SQL scripts

**Location.** `docker-compose.yml:9-10`

```yaml
    volumes:
      - ./sql:/docker-entrypoint-initdb.d
```

**Analysis.** The official PostgreSQL image's *entrypoint* runs every `.sql` in that directory **in alphabetical order** on an empty volume. The resulting order:

```
1. 01_init.sql
2. apply_cache.sql
3. apply_evaluator.sql
4. apply_graphrag.sql
5. apply_memory.sql
6. apply_rls.sql
7. create_app_user.sql      ← creates the app_user role
```

The four table `apply_*.sql` scripts end with a `GRANT`:

```sql
GRANT ALL PRIVILEGES ON TABLE semantic_cache TO app_user;     -- apply_cache.sql:20
GRANT ALL PRIVILEGES ON TABLE rag_evaluations TO app_user;    -- apply_evaluator.sql:19
GRANT ALL PRIVILEGES ON TABLE knowledge_graph TO app_user;    -- apply_graphrag.sql:21
GRANT ALL PRIVILEGES ON TABLE user_memory TO app_user;        -- apply_memory.sql:20
```

but `app_user` does not exist until step 7.

**Failure observed.** A `docker compose up -d` on a clean volume aborts at step 2:

```
ERROR:  role "app_user" does not exist
```

The official image's entrypoint treats init errors as fatal: the container exits and the database is left with `01_init.sql` applied and nothing else.

**Why it was not caught.** `PAPER_PLAN.md` §1 describes the `apply_*.sql` scripts as *"individual iterative migration scripts used during development"*. They were run by hand, in logical order, on an existing database where `app_user` had already been created. The failure only shows up in a new environment, that is, for anyone who clones the repository.

**Two related gaps in the same place.**

1. **`01_init.sql` does not create `knowledge_graph`.** The table only exists in `apply_graphrag.sql`. If the order were fixed by running only `01_init.sql`, GraphRAG would fail at runtime with `relation "knowledge_graph" does not exist`. `PAPER_PLAN.md` §1 describes it as the *"unified script that creates the tables"*; it is not.

2. **`01_init.sql` does not apply `FORCE ROW LEVEL SECURITY`.** The four tables get `ENABLE ROW LEVEL SECURITY`, but without `FORCE` **the table owner bypasses its own policies**. Only `create_app_user.sql:6` applies `FORCE`, and only to `documents`. The others depend on their respective `apply_*.sql` scripts, the ones that fail. Combined with the `.env.example` DSN (user `postgres`, which owns everything), multi-tenant isolation is **switched off in practice**. See `DOC-03`.

**Reproduction.**

```bash
ls sql/ | sort
grep -n "app_user" sql/*.sql
grep -c "FORCE ROW LEVEL SECURITY" sql/01_init.sql   # 0
grep -n "knowledge_graph" sql/01_init.sql            # no matches
```

**Patch.** Rename with a numeric prefix that reflects the real dependencies:

```
00_create_app_user.sql     (formerly create_app_user.sql, without the ALTER TABLE documents)
01_init.sql                (+ knowledge_graph, + FORCE on the 5 tables, + GRANTs)
02_migrations/             (the apply_*.sql scripts, out of initdb: they are migration history)
```

`create_app_user.sql` must lose its last line (`ALTER TABLE documents FORCE ROW LEVEL SECURITY`), which refers to a table that does not exist yet if the role is created first. That `FORCE` belongs in `01_init.sql`, together with those of the other four tables.

Also add to `docker-compose.yml` the healthcheck `ROADMAP_PHASE_5_SCALABILITY.md` §1 already plans for, so the init failure is visible:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
```

**Status: ✅ fixed (2026-09-14).** The layout is as the patch proposes: `00_create_app_user.sql` without its `ALTER TABLE`, a full `01_init.sql` and the `apply_*.sql` scripts in `sql/migrations/` (the entrypoint ignores subdirectories). There are four adjustments:

- **`01_init.sql` reproduces the development database exactly**, which is the one the application works against. It includes `knowledge_graph`, `FORCE` on the five tables and the `GRANT`s, and it also creates the indexes **with the names they have in development**. The `apply_*.sql` scripts created named indexes and the previous `01_init.sql` created them without a name, so running both would have duplicated every HNSW index.
- **TCP healthcheck** (`pg_isready -h 127.0.0.1`) and not over the socket, as the patch had it. The entrypoint starts the temporary init server with `-c listen_addresses=''` (`docker-entrypoint.sh:297`). Over the socket it would answer while the scripts are running; over TCP, only once they have finished.
- **Correction to point 2.** `FORCE` does not rescue the `.env.example` DSN. `postgres` is a superuser, and a superuser bypasses RLS **with or without `FORCE`** (verified below). `FORCE` does subject a non-superuser owner to the policies. Isolation requires the application to connect as `app_user`, which is still pending in `DOC-03`.
- **References updated** in `PAPER_PLAN.md`, `GRAPHRAG_ARCHITECTURE.md` and both papers (Spanish and English). The papers' citation of *"`01_init.sql`, lines 42-44"* was already wrong before the change: it pointed to the cache policy, not to the `CHECK`s of `rag_evaluations`.

Verified with the real `docker-compose.yml`, with another project name and another port through an override, on an empty volume and without touching the development database:

| Test | Before | After |
|---|---|---|
| Bootstrap from scratch | The container exits with `exit=3` after 2 s: `apply_cache.sql:20: ERROR: role "app_user" does not exist` | `00_create_app_user.sql` → `01_init.sql`, `ignoring …/migrations`, `healthy` at 5.3 s, no errors. Reproduced twice |
| Catalog fingerprint against the development database: columns (without position), indexes, constraints, policies, RLS/`FORCE`, grants and ACL | — | **Identical**: 77 of 77 lines |
| RLS as `app_user` | — | 7/7. Each tenant sees only its own, without a tenant it sees nothing and cross writes are rejected. The superuser sees everything despite `FORCE`, and a non-superuser owner sees 0 rows with `FORCE` and 2 without it |
| Real application (ingestion + `/chat/`) against the new database | — | 6/6. 1 chunk and 7 triples ingested; the answer cites the document with confidence 1.0; the cache and the evaluation are written under the token's tenant; the development database stays intact |

An observation from the last test: `rag_evaluations` got a row. The evaluator does not always fail: with a single-document context, the judge's answer fits in `max_tokens=300`. With the real corpus context it does not fit (`PERF-04`), and that is why the development database has no evaluation.

---

### `BUG-05` 🟡 The self-correction loop corrects nothing

**Location.** `src/services/agent_graph/graph.py:11-18`

```python
def route_reviewer(state: AgentState) -> str:
    # Si Claude indicó que requiere más info y no hemos iterado demasiado
    if state.get("needs_more_info") and state.get("iterations", 0) < 2:
        print("🔄 [Revisor] Falta contexto. Volviendo al Investigador con instrucciones extendidas...")
        # NOTA: En una implementación más avanzada, aquí modificaríamos 'search_queries'
        # para que busque algo más específico. Por ahora, solo re-itera.
        return "researcher"
    return "END"
```

**Analysis.** The decision mechanism is correct and well wired: `generate_answer` returns `StructuredAnswer.requires_more_info`, `generator_node` maps it to `state["needs_more_info"]` (`nodes.py:115`), and `route_reviewer` reads it. The iteration guard works: `researcher_node` increments the counter (`nodes.py:95`) and the limit of 2 prevents infinite loops.

The problem is what happens **after** going back. `researcher_node` (`nodes.py:61-95`) reads `state["search_queries"]` (which no node has modified) and runs:

```python
retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=15) for q in queries]
```

The same queries, against the same database, with the same `top_k`. The vector search and FTS are deterministic. Re-ranking is deterministic. The result is **byte for byte identical** to the first iteration's.

The generator gets the same context, and being an LLM with the default temperature (1.0, according to `PAPER_PLAN.md` §3.4) there is a non-zero chance that this time it does not flag `requires_more_info`, but that is sampling noise, not correction.

The printed message (*"Volviendo al Investigador con instrucciones extendidas"*, "Back to the Researcher with extended instructions") describes something that does not happen: there are no extended instructions.

**Measured cost of a pointless iteration:**

| Resource | Cost |
|---|:---:|
| Postgres connections | +6 (5 retrieval + 1 graph) |
| FlashRank calls | +1 (over ~75 candidates) |
| Claude calls | +1 (full generation, `max_tokens=8192`) |
| Latency | ~2× that of a normal query |

**Impact on the documentation.** The code comment is honest. `PAPER.md` §5.4, on the other hand, formalizes it as a state machine with working *self-correction*, and §4.3.3 describes the generator *"conceptually acting as the Reviewer"*. The `README.md` is the most explicit:

> *"Reasoning loops: if the Generator agent detects that the retrieved context is insufficient, it rejects the generation and hands control back to the Researcher to run deeper queries."*

The queries are not deeper: they are the same.

**Reproduction.**

```bash
sed -n '11,18p' src/services/agent_graph/graph.py
sed -n '61,72p' src/services/agent_graph/nodes.py   # queries unchanged
```

**Patch.** Two options, and it is best to choose explicitly.

**(a) Make the loop contribute something**: widen the search on every retry. It is the minimal change with a real effect:

```diff
--- a/src/services/agent_graph/nodes.py
+++ b/src/services/agent_graph/nodes.py
@@ async def researcher_node(state: AgentState) -> dict:
     queries = state["search_queries"]
+    iteration = state.get("iterations", 0)
+    # On retries, widen the retrieval window and relax the re-ranking:
+    # the generator already told us the narrow context was not enough.
+    retrieve_k = 15 + (15 * iteration)
+    rerank_k = 10 + (5 * iteration)

-    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=15) for q in queries]
+    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=retrieve_k) for q in queries]
@@
-    best_results = await rerank_documents(state["query"], unique_candidates, top_k=10)
+    best_results = await rerank_documents(state["query"], unique_candidates, top_k=rerank_k)
```

More ambitious: call `analyze_query` again asking for different variants, passing it the ones already tried as negatives.

**(b) Disable the loop and align the documentation**: if (a) is not going to be implemented, the honest thing is `iterations < 1` (it never iterates) and rewriting the README and `PAPER.md` §5.4 to describe the `requires_more_info` flag as what it is: a quality signal reported to the user, not a correction mechanism.

**Status: ✅ fixed (2026-09-14), option (a), chosen by the user.** `researcher_node` computes its window with `retrieval_window(base_retrieve, base_rerank, iteration)`. There are three differences from the patch above:

- **The base is the client's `top_k`**, which `BUG-06` made effective, and not a fixed 15/10. Each retry multiplies the candidates per variant and lets 50% more documents through, rounding up: 15/10 → 30/15, 15/3 → 30/5, 15/1 → 30/2. The ceiling is the API maximums (`MAX_TOP_K_RETRIEVE=50`, `MAX_TOP_K_RERANK=20`, now constants in `requests.py`), so the loop respects the same cost bound as a request.
- **No pointless retries.** The researcher sets `retrieval_exhausted` when a larger window cannot change the context: no search filled its quota and the generator already got every candidate, or the next window is the same because of the maximums. In that case `route_reviewer` ends even if the generator asks for more information. With small corpora, like this sandbox's (11 documents per tenant), it is the common case.
- **The message says what happens** (*"Back to the Researcher with a wider search"*), and the retry prints the window it uses. The README, `PAPER_PLAN.md` and both papers now describe the widening and the new exit condition.

Verified against a real uvicorn, with the real graph, LLM and Postgres. The search, the re-ranking and the generator were wrapped only to record, on each pass, the window, the documents (with their IDs) and whether the generator asked for more information. A low `top_k_rerank` reliably triggers the retry:

| Scenario | Before | After |
|---|---|---|
| No parameters (positive control) | 1 pass, 15/10 | 1 pass, 15/10 |
| `/chat/`, `top_k_rerank=1` | 2 **identical** passes: 15/1, same document | 15/1 → **30/2**, 1 new document |
| `/chat/stream/`, `top_k_rerank=3` | 2 **identical** passes: 15/3, same documents | 15/3 → **30/5**, 2 new documents |
| Question with no answer in the corpus, context already exhausted (11 < 15 and 11 ≤ 20) | 2 identical passes | **1 pass**: no retry |
| A retry repeats the previous search | 3 of 3 | 0 |
| **Checks** | **3/7** | **7/7** |

Separately, 18 direct cases without a database or LLM: the window (including the caps 30/15 → 50/20 and 50/20 → 50/20), the five branches of `route_reviewer` and the exhaustion flag with simulated corpora of 11 and 100 documents. The database was returned to its initial state.

**Limits of what was measured.** The retry brings new context, but it does not guarantee the generator is satisfied: in the two scenarios with a retry it asked for more information again. With this corpus, widening the search (15 → 30) added no candidates, because each tenant has 11 documents; the new documents came from widening the re-ranking. The effect of the search with a larger corpus is covered by the direct cases, not measured against the real database. The more ambitious alternative, rewording the queries on the retry, is not implemented.

---

### `BUG-06` 🟡 `top_k_retrieve` / `top_k_rerank` are decorative

**Location.** `src/models/requests.py:4-8` declares them as the API's public contract:

```python
class ChatRequest(BaseModel):
    query: str
    history: List[Dict[str, str]] = Field(default_factory=list, ...)
    top_k_retrieve: int = 15
    top_k_rerank: int = 7
```

`src/services/agent_graph/nodes.py:70` and `:83` ignore them:

```python
retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=15) for q in queries]
best_results = await rerank_documents(state["query"], unique_candidates, top_k=10)
```

**Analysis.** The API accepts both parameters, Pydantic validates them, and they are silently discarded. A client sending `top_k_rerank: 3` gets exactly the same behavior as one sending `top_k_rerank: 50`.

Note also that the values do not even match: the contract declares `top_k_rerank: int = 7` and the code uses `10`.

**Why it matters more than it seems.** `TROUBLESHOOTING.md` §2 documents a real bug (*"the re-ranker drops vital information"*) and records as part of the solution:

> *"Wider context window: `src/models/requests.py` was changed to raise `top_k_rerank` from 3 to 7."*

That documented solution **has no effect today**. If the problem came back, someone following the post-mortem would adjust an inert value. It is worse than a missing parameter: it is a lever that seems to work.

(The other half of the §2 solution, deduplication by `content` and widening to 15 candidates, did survive the migration, in `nodes.py:74-80` and `:70`.)

**Reproduction.**

```bash
grep -rn "top_k_retrieve\|top_k_rerank" src/
# only match: src/models/requests.py:7-8 (definition)
```

**Patch.** Pass them through the state, like `BUG-03`:

```diff
--- a/src/services/agent_graph/state.py
+    top_k_retrieve: int
+    top_k_rerank: int

--- a/src/api/routers/chat.py   (in both initial_state)
+            top_k_retrieve=request.top_k_retrieve,
+            top_k_rerank=request.top_k_rerank,

--- a/src/services/agent_graph/nodes.py
-    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=15) for q in queries]
+    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=state.get("top_k_retrieve", 15)) for q in queries]
-    best_results = await rerank_documents(state["query"], unique_candidates, top_k=10)
+    best_results = await rerank_documents(state["query"], unique_candidates, top_k=state.get("top_k_rerank", 10))
```

Align the `top_k_rerank` default to 10 (or justify 7). If `BUG-05` option (a) is implemented, these values become the base that is widened on each iteration.

Alternative: remove them from `ChatRequest` if they are not meant to be exposed, and correct the note in `TROUBLESHOOTING.md` §2.

**Status: ✅ fixed (2026-09-14).** Passing them through was chosen, as the patch proposes, because `TROUBLESHOOTING.md` §2 presents them as the lever that fixed a real failure. They travel through the state to `researcher_node`, on both endpoints. There are four adjustments:

- **A single place for the defaults.** `DEFAULT_TOP_K_RETRIEVE = 15` and `DEFAULT_TOP_K_RERANK = 10` live in `requests.py`, and both the node and the router import them. The divergence between the contract's 7 and the code's 10 was the defect itself. 10 is chosen because it is what the application did and what `PAPER_PLAN.md` documents, so a client that sends no parameters notices no change.
- **Range limits:** `top_k_retrieve` between 1 and 50, and `top_k_rerank` between 1 and 20. Without them, once passed through, a 0 or a negative would reach a Postgres `LIMIT`, and a huge value would multiply the cross-encoder's cost, because the search is repeated for every query variant.
- **Cache.** `semantic_cache` is keyed only by the question, so an answer obtained with other `top_k` values is not interchangeable with the one from the defaults. Requests that change them neither read nor write the cache. Without this, the lever would still have no effect as soon as the question was cached.
- **A note added in `TROUBLESHOOTING.md` §2.**

Verified against a real uvicorn, with the real graph, LLM and Postgres. `retrieve_documents` and `rerank_documents` were wrapped only to record the `top_k` they receive and how many documents they return. The test tenant has 11 documents.

| Scenario | Before | After |
|---|---|---|
| No parameters (positive control) | 15 / 10 | 15 / 10 |
| `top_k_retrieve=2`, `top_k_rerank=3` | 15 / 10: ignored | 2 candidates per variant / 3 documents |
| `top_k_rerank=1` | 10 documents | 1 document |
| `/chat/stream/` with `top_k_rerank=2` | 10 documents | 2 documents |
| `top_k_rerank=0`, `top_k_retrieve=-1`, `1000` | HTTP 200: silently discarded | HTTP 422 |
| Cached question with `top_k_rerank=3` | Served from the cache | Runs the graph with 3 and does not write the cache |
| Cached question without parameters | Cache hit | Cache hit |
| **Checks** | **3/8** | **8/8** |

Separately, 12 direct cases: the exact validation edges (1/50/51 and 1/20/21), the defaults (15, 10) and a graph state without the keys, which falls back to 15/10. The database was returned to its initial state; the evaluator wrote two rows in the background, which were purged too.

**Side evidence about `BUG-05`.** With 1 to 3 documents, the generator asked for more information and the self-correction loop made a second researcher pass **with the same `top_k`**: 8 identical searches and 2 identical re-rankings. The retry widens nothing.

---

### `BUG-07` 🟡 The only test suite cannot run

**Location.** `tests/test_rag.py:28`

```python
vector_candidates = await retrieve_documents(query, top_k=5)
```

**Analysis.** The current signature of `retrieve_documents` (`retriever.py:20`) is:

```python
async def retrieve_documents(query: str, tenant_id: str, top_k: int = 5) -> List[SearchResult]:
```

`tenant_id` is the second **required positional** parameter, introduced in Phase 3 with multi-tenancy. The test's call raises `TypeError: retrieve_documents() missing 1 required positional argument: 'tenant_id'` before evaluating anything.

Line 32 has the same potential problem: `generate_answer(query, best_results)` leaves out `user_profile`, although there the parameter has a default (`extractor.py:15`) and does not break.

`src/pipeline.py:13` fails the same way.

**Impact.** The repository **has no runnable test coverage**. This contradicts `ARCHITECTURE.md` §6, which presents this suite as the project's "automatic evaluation system", and the `README.md`, which lists *"deterministic evals (DeepEval)"* as a Phase 1 achievement.

`PAPER_PLAN.md` §5.2 correctly marks it as *"obsolete Phase 1 evals"*, but the file is still in `tests/` with no sign of it in the code itself.

**An important clarification.** The LLM-as-a-judge evaluator in `src/services/evaluator.py` **does not replace these tests**. They are different, complementary mechanisms: the evaluator scores answers in production (observability), the tests check that the pipeline works before deploying it (regression). Losing the latter is not made up for by the former.

**Reproduction.**

```bash
PYTHONPATH=. uv run pytest tests/ -x
# TypeError: retrieve_documents() missing 1 required positional argument: 'tenant_id'
```

**Minimal patch to make it run again:**

```diff
+TEST_TENANT = "00000000-0000-0000-0000-000000000000"
+
 @pytest.mark.asyncio
 async def test_rag_contextual_relevancy_and_faithfulness():
     query = "¿Para qué sirve el archivo pyproject.toml?"
-    vector_candidates = await retrieve_documents(query, top_k=5)
+    vector_candidates = await retrieve_documents(query, TEST_TENANT, top_k=5)
     best_results = await rerank_documents(query, vector_candidates, top_k=3)
```

It also requires `pytest-asyncio` (not declared; see `HYG-01`) and a populated database, so it is an integration test, not a unit test. The coverage most needed is unit-level and needs no infrastructure:

- `chunk_text()` on a synthetic text with two clearly separate topics → check that it cuts at the topic boundary and respects `max_tokens`.
- `route_supervisor` / `route_reviewer` on hand-built state dictionaries → check the transitions without touching the network (it would cover `BUG-05` as a regression).
- `cosine_distance()` with known vectors, including the zero-norm case (`ingestion.py:43`).

**Status:** ✅ fixed on 2026-09-16. It is the first finding worked as an OpenSpec change (`openspec/changes/regression-test-suite/`: proposal, spec, design and tasks).

**The entry fell short.** The minimal patch above no longer applied: `retrieve_documents` now takes a `uuid.UUID`, not a string. And fixing the `TypeError` would not have been enough. DeepEval uses OpenAI as the default judge, with no key configured. The test's question (*pyproject.toml*) has no answer in the corpus, which is a résumé. And even if it passed, it would protect none of this audit's fixes. By the user's decision, the suite is redirected to **regression**, and quality evaluations are left for a separate change.

**What there is now.**

| Layer | Where | What it needs | Tests | Time |
|---|---|---|:---:|:---:|
| 1. Pure logic | `tests/unit/` | nothing: no DB, no LLM, no `.env`, no Docker | 71 | ~0.3 s |
| 2. Real Postgres | `tests/db/` | Docker; it starts and deletes its own database | 18 | ~8 s |
| Evals | `tests/evals/` | only with `--run-evals`; `test_rag.py` is still unfixed | — | — |

- **Layer 1:** cache policy (`BUG-02`, `BUG-06`, `BUG-10`), window, exhaustion and the reviewer's decision (`BUG-05`), history (`BUG-03`), file name (`SEC-04`), the judge's scores (`DOC-02`) and the tenant signature (`SEC-05`). A guard test fails if any pure module pulls in `sentence_transformers`, `flashrank`, `anthropic` or `langgraph`.
- **Layer 2:** isolation with a signed context (`SEC-05`), GraphRAG with a permissive tokenizer (`SEC-03`), transaction-local tenant and reused connection (`PERF-01`), `app_user`'s privileges (`HYG-07`, `SEC-07`, including the `pg_db_role_setting` watch left pending in `SEC-07`) and bootstrapping from an empty volume (`BUG-04`).
- **Extractions in production code, without changing behavior:** so that layer 1 does not pay the ~10 s of importing `chat.py` and `nodes.py`, they were moved to modules without import side effects: `cache_policy.py`, `agent_graph/routing.py`, `filenames.py` and `models/evaluation.py`. Two pieces were written inline (the exhaustion decision and the name sanitizing). Checked: the same tests green before and after, the compiled graph identical, 4,900 combinations of the exhaustion check with no differences, the same JSON schema for the judge, and the real API against the development database (with history, no cache; without history, it writes; repeated, a hit in 0.0 s).

**Guarantees about the development database.** `tests/conftest.py` sets `DATABASE_URL` to port 5439 before importing anything from `src`, because `db.py` pins its database at import time, with development as the default. A guard aborts the session if `DB_DSN` does not point to the test database: checked by importing `db.py` earlier from a plugin, it exits with code 1 without starting anything. In a full run with development up, 173 samples of `pg_stat_activity` recorded 0 network connections to development (the positive control does detect one), with the same counts, container and volume.

**Lifecycle of the disposable database.** Compose project `sandbox_tests`, volume `sandbox_tests_pgdata` deleted by exact name and only if it belongs to that project. After a failed test nothing is left behind. After a `kill -9` the container and the volume remain, and the next run cleans them up when it starts. Without Docker (daemon unreachable or no binary), the full suite exits with code 1 and *"Could not start the test database"*, and `tests/unit` alone passes.

**Negative control: 22 of 22.** Each defect was reintroduced in the code or in `sql/`, its layer was run and the change was restored.

| Finding | Reintroduced | Failing |
|---|---|:---:|
| `BUG-02` | cache any answer / remove the allowlist | 10 / 5 |
| `BUG-06` | ignore custom `top_k` / remove `ge`/`le` | 3 / 3 |
| `BUG-10` | ignore the history | 1 |
| `BUG-05` | fixed window / reviewer without exhaustion / never exhausted / no cap | 7 / 1 / 3 / 6 |
| `BUG-03` | discard the history / no window / `msg["role"]` | 2 / 1 / 3 |
| `SEC-04` | name as is / `basename` without normalizing `\` | 8 / 2 |
| `DOC-02` | scores without `ge`/`le` | 6 |
| `SEC-05` | policies on `current_setting` without a signature | 5 |
| `SEC-03` | `WHERE` by concatenation | 2 |
| `PERF-01` | `set_config(..., false)` | 1 |
| `HYG-07` | `ALTER DEFAULT PRIVILEGES` back | 1 |
| `SEC-07` | `GRANT ALL` on the database / stored `ALTER ROLE ... SET search_path` | 1 / 1 |
| `BUG-04` | `00_create_app_user.sql` renamed to `02_` | session with code 1 |

Two spec scenarios were added during implementation, because without them the test did not catch its defect coming back. With concatenation in GraphRAG, the cross-tenant read is **still blocked** by the `SEC-05` signature: only the tautology and the apostrophe tell `SEC-03` apart. With `set_config(..., false)`, asyncpg's `RESET ALL` **hides** the leak in the real pool: a pool without reset is needed to check our own defense.

**Configuration.** `pytest` and `pytest-asyncio` move to the `dev` group (with `--no-sync`, see `HYG-01`). `testpaths = ["tests"]`, so the root's `test_*.py` (`HYG-02`) are no longer collected. Also `-p no:deepeval`: its plugin loaded on every run (~1.7 s, it imports `anthropic` and `openai`). The suite runs with `uv run pytest`, and the pure layer alone with `uv run pytest tests/unit`.

**Added later.** The API layer with doubles arrived on 2026-09-17 with the `api-regression-layer` change: 40 more tests, with a 9 of 9 negative control, which pin `SEC-01`, `SEC-02`, `SEC-06`, `BUG-01` and `BUG-09` at the HTTP edge. Closing it turned up `HYG-09`.

**Outside that change.** The quality evals (`test_rag.py`, the judge, `deepeval` in production, the README's claim). The `chunk_text` and `cosine_distance` tests the entry suggested, which protect no fix and live in a module that loads models. The performance and Docker measurements (`PERF-02` to `PERF-04`, `DOC-01`, `HYG-06`, `HYG-08`, `DOC-03`), which remain manual.

---

### `BUG-08` 🟠 The re-ranker cache lives in `/tmp` and losing it leaves the app unable to start

**Location.** `src/services/reranker.py:10`

```python
ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp/flashrank")
```

**Symptom.** The FastAPI process does not start. The traceback ends in:

```
onnxruntime.capi.onnxruntime_pybind11_state.NoSuchFile: [ONNXRuntimeError] : 3 : NO_SUCHFILE :
Load model from /tmp/flashrank/ms-marco-MiniLM-L-12-v2/flashrank-MiniLM-L-12-v2_Q.onnx failed.
File doesn't exist
```

The error points to a file whose download and management are the library's own responsibility, which makes the diagnosis far from obvious: nothing in the project's code mentions that `.onnx`.

**Cause, verified in FlashRank's source.** `Ranker._prepare_model_dir` (`flashrank/Ranker.py:76-83`) decides whether to download by checking only that the **directory** exists, never the model file:

```python
if not self.cache_dir.exists():
    self.cache_dir.mkdir(parents=True, exist_ok=True)

if not self.model_dir.exists():
    self.logger.info(f"Downloading {model_name}...")
    self._download_model_files(model_name)
```

The failure mode follows: **if the model directory survives but its contents disappear, FlashRank never downloads again** and `ort.InferenceSession` (l. 68) fails when it is built. Since the instantiation is at module level, the failure happens at import time and takes down the whole API startup.

It is a **permanent** state: retrying, restarting or reinstalling dependencies does not recover it. The directory has to be deleted by hand.

**Why the contents disappear.** `/tmp` is volatile storage by definition, and when it is emptied depends on the system (reboot, maintenance tools, cleanup policies). On the audited machine the `ms-marco-MiniLM-L-12-v2/` directory was found **empty**, with a timestamp of 00:00 on the day of the audit; which process emptied it could not be determined (`/etc/periodic/daily/` does not exist in this version of macOS), and the exact mechanism is irrelevant to the defect: the guarantee the code assumes (that `/tmp` persists) does not exist on any platform.

**Confirmation that it predates and is independent of other changes.** Reproduced with `git stash` on the clean tree: identical failure, same traceback, with the original code.

**Behavior by environment.**

| Environment | What is lost | Consequence |
|---|---|---|
| Development macOS / Linux | Only the files; the directory survives | ❌ **The app does not start, permanently** |
| Container with `/tmp` on tmpfs | The whole tree | ⚠️ Re-download on every start: a network dependency at boot and a slow cold start |
| CI / ephemeral runner | The whole tree | ⚠️ Download on every pipeline run |

None of the three columns is acceptable for epic 1 of [`ROADMAP_PHASE_5_SCALABILITY.md`](history/ROADMAP_PHASE_5_SCALABILITY.md): an image that downloads its inference model from the internet on every start cannot be deployed *serverless* (Cloud Run, ECS), where cold starts are frequent and outbound internet access may be restricted.

**Mitigating factor.** The value is not arbitrary: `default_cache_dir = "/tmp"` in `flashrank/Config.py:6` is the library's own default. The project inherited a bad upstream convention, it did not invent it. But since it passes `cache_dir` explicitly, changing it costs the same as leaving it.

**A related landmine.** The audited machine also has an empty `/tmp/flashrank/ms-marco-TinyBERT-L-2-v2/` directory: FlashRank's **default** model, the same one that, according to [`PAPER.md`](PAPER.md) §9.2, returned 404 and forced the switch to `MiniLM-L-12-v2`. By the same directory-existence logic, any code that instantiates `Ranker()` with default parameters will fail with `NO_SUCHFILE` instead of trying the download, reproducing the original 404 as a different and more confusing error.

**Relation to `TROUBLESHOOTING.md` §3.** That post-mortem documents the symptom *"the backend is down"* and attributes it to the model loading window with `--reload` and to zombie processes. This finding is a **third cause of the same symptom**, qualitatively different: it is not a window of a few seconds during startup, but a permanent state in which startup never completes.

**Reproduction.**

```bash
# Cause the state (destroys the model cache):
rm -f /tmp/flashrank/ms-marco-MiniLM-L-12-v2/*
PYTHONPATH=. uv run python -c "import src.services.reranker"
# → NO_SUCHFILE, and it will keep happening indefinitely

# Check the mechanism in the library's source:
sed -n '76,83p' .venv/lib/python3.14/site-packages/flashrank/Ranker.py
grep -n "default_cache_dir" .venv/lib/python3.14/site-packages/flashrank/Config.py

# Manual unblocking (forces the re-download):
rm -rf /tmp/flashrank/ms-marco-MiniLM-L-12-v2
```

**Patch.** Move the cache to a persistent, configurable location:

```diff
--- a/src/services/reranker.py
+++ b/src/services/reranker.py
@@
+import os
+from pathlib import Path
+
+# /tmp is volatile and FlashRank decides whether to download by looking only at
+# whether the model DIRECTORY exists: if its contents disappear but the directory
+# stays, it never downloads again and the app stops starting for good.
+RERANKER_CACHE_DIR = os.getenv(
+    "RERANKER_CACHE_DIR", str(Path.home() / ".cache" / "flashrank")
+)
+
 print("Cargando modelo local de Re-ranker (FlashRank)...")
-ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp/flashrank")
+ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir=RERANKER_CACHE_DIR)
```

A complementary defense, because the persistent directory can get corrupted too (interrupted download, full disk): check that the file exists, not just the directory, and clean up before instantiating.

```python
from flashrank.Config import model_file_map

_model_dir = Path(RERANKER_CACHE_DIR) / "ms-marco-MiniLM-L-12-v2"
_model_file = _model_dir / model_file_map["ms-marco-MiniLM-L-12-v2"]
if _model_dir.exists() and not _model_file.exists():
    # Directory present with no model inside: FlashRank would never re-download.
    shutil.rmtree(_model_dir)
```

For epic 1 (containerization), the right solution is different and stronger: **download the model at build time**, not at startup. In the `Dockerfile`, a layer that instantiates the `Ranker` once leaves the model baked into the image, removes the network dependency at boot and makes the cold start deterministic:

```dockerfile
ENV RERANKER_CACHE_DIR=/opt/models/flashrank
RUN python -c "from flashrank import Ranker; \
    Ranker(model_name='ms-marco-MiniLM-L-12-v2', cache_dir='/opt/models/flashrank')"
```

**Status: ✅ fixed (2026-09-11).** The cache moved to `~/.cache/flashrank` (configurable through `RERANKER_CACHE_DIR`) and `_ensure_model_cache()` was added, which cleans up a model directory that exists without the file inside. Verified in the three scenarios: healthy cache (loads in 0.78 s without downloading), corrupt cache (detected and re-downloaded instead of failing) and override through the environment variable. The already downloaded model was migrated from `/tmp` at no network cost, and the empty `ms-marco-TinyBERT-L-2-v2` directory was removed.

---

### `BUG-09` 🟠 `/chat/stream/` returns no answer for greetings, out-of-scope topics or tools

> A finding after the audit, found on 2026-09-13 while rewriting the streaming loop for `DOC-01`. It is not part of the counts in §1, which are the 2026-09-10 snapshot.

**Location.** `src/api/routers/chat.py:102-120` (code from before the `DOC-01` fix)

**Symptom.** A greeting through the streaming endpoint returns **a single SSE event with the progress line and nothing else**:

```
SSE events: 1
  answer='🤖 *Supervisor evaluando estrategia...*\n\n'  confidence=None
```

The same question through `/chat/` answers correctly. The affected endpoint is precisely the one the frontend uses (`app.py:90` POSTs to `/chat/stream/`), so the defect shows up in the real application and not on the secondary path.

**Cause.** The supervisor resolves three of the four intents on its own (`casual_greeting`, `out_of_scope` and `tool_execution`), returning `final_answer` and routing to `END` without going through the generator (`nodes.py:28-55`, `graph.py:5-9`). The stream loop, however, only read `final_answer` inside the `node_name == "generator"` branch:

```python
elif node_name == "generator":
    ...
    if "final_answer" in state_update and state_update["final_answer"]:
```

When the graph ends at the supervisor that branch never runs, so the answer stays in the state and never reaches the client. As a side effect, `final_dict` stays `None` and nothing is stored in the semantic cache either.

**Scope.** The three tools (`get_current_time`, `get_crypto_price`, `get_github_profile`), greetings and out-of-scope questions. That is, everything that is not `knowledge_search`.

**Why the audit did not catch it.** §5 reviewed the streaming loop looking for cache pollution (`BUG-01`) and the history path (`BUG-03`), both on the `knowledge_search` path. The other three paths were verified on `/chat/`, where they work. It is a reminder that coverage per endpoint is not coverage per graph branch.

**Reproduction.**

```bash
# With the cache purged, so it does not intercept:
curl -N -X POST http://127.0.0.1:8000/chat/stream/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query": "Hola, qué tal", "history": []}'
# → a single event, only the progress line
```

**Fix.** Move the reading of `final_answer` out of the generator branch, and append the text to the accumulated one when the node that produced it is not the generator (the generator already emitted its text on the `custom` channel):

```python
if state_update and state_update.get("final_answer"):
    final_dict = state_update["final_answer"].model_dump()
    if node_name != "generator":
        accumulated_answer += final_dict.get("answer") or ""
    yield f"data: {json.dumps({**final_dict, 'answer': accumulated_answer})}\n\n"
```

**Status: ✅ fixed (2026-09-13).** Fixed together with `DOC-01`, since it sits in the same loop. Verified: the greeting returns the supervisor's text and `get_current_time` returns its result, both through the stream.

---

### `BUG-10` 🟠 The semantic cache ignores the history

> After the snapshot: detected on 2026-09-14 while fixing `BUG-02`. **Verified by reading the code; not reproduced end to end.**

**Location.** `src/services/cache.py:17` (`check_semantic_cache(tenant_id, query, threshold)`) and `:46` (`save_semantic_cache(tenant_id, query, response_dict)`). The four calls are in `src/api/routers/chat.py:52`, `:86`, `:108` and `:175`.

**Analysis.** Since the `BUG-03` fix, the answer depends on the history: *"¿Y en qué años?"* ("And in which years?") is resolved against the previous turn, both in the supervisor and in the generator. But the cache is read and written with the question text alone. If two conversations of the same tenant end in the same follow-up, they share a cache entry: the second gets the first's answer, about another referent.

Follow-up questions are short and generic, exactly the ones that collide most. If the text is identical, the similarity is 1.0. Within a tenant, moreover, a user can get an answer built from another user's conversation.

`BUG-02` and `BUG-06` restricted what is cached (intent, confidence, `top_k`), but neither takes the history into account.

**Scenario.**
1. Conversation A: *"¿Dónde trabajó en 2024?"* ("Where did he work in 2024?") → Betterfly. *"¿Y en qué años?"* → answered about Betterfly and cached.
2. Conversation B: *"¿Qué hizo en Itaú?"* ("What did he do at Itaú?") → … *"¿Y en qué años?"* → cache hit with similarity 1.0: it gets Betterfly's years.

**Reproduction.**

```bash
grep -n "def check_semantic_cache\|def save_semantic_cache" src/services/cache.py   # they get no history
grep -n "semantic_cache(" src/api/routers/chat.py                                    # only request.query
```

**Patch.** The minimum is not to read or write the cache when the request carries history, as with custom `top_k`:

```python
use_cache = uses_default_retrieval(request) and not request.history
```

The alternative keeps the cache for follow-ups: key it by the `search_queries` the supervisor already resolved, which carry the referent explicitly. It forces the cache to be checked after the supervisor, not before, and costs one LLM call per cached request.

**Status:** ✅ fixed on 2026-09-16 with the minimal patch, which is the one the user chose.

**It was first reproduced end to end**, which is what the finding lacked. Against the real API and DB, as `company_x`, with two referents that exist in the corpus and the cache purged beforehand:

| | Conversation A | Conversation B |
|---|---|---|
| Turn 1 | *"¿Qué hizo Bryan en MisterGas?"* ("What did Bryan do at MisterGas?") → June 2020 – September 2022 | *"¿Qué hizo Bryan en Itaú/Kabeli?"* ("What did Bryan do at Itaú/Kabeli?") → May 2023 – March 2024 |
| Turn 2 (identical) | *"¿Y en qué años fue eso?"* ("And in which years was that?") → **June 2020 to September 2022** | *"¿Y en qué años fue eso?"* → **June 2020 to September 2022** |

B's turn 2 answer was **byte for byte** A's, with a `✅ Cache Hit` in the server log. The finding's scenario holds exactly as described.

**The effect was worse than the analysis said.** The answer served from the cache starts with *"Según el historial anterior, Bryan trabajó en MisterGas (Lipigas)…"* ("According to the previous history, Bryan worked at MisterGas (Lipigas)…"): it does not just deliver the wrong referent's data, it attributes it to a history that is not that of the user who receives it. Wrong data presented with the authority of the conversation itself.

**Patch applied.** `is_cache_eligible(request)` in `src/api/routers/chat.py`, used by both endpoints: `uses_default_retrieval(request) and not request.history`. With it, the same script gives different and correct answers in each conversation (B answers *"Itaú/Kabeli … from May 2023 to March 2024"*), **0 cache hits**, and `semantic_cache` holds only the first two questions, the ones without history.

**Why not the alternative.** Keying by the supervisor's `search_queries` only closes the defect if the supervisor always embeds the full referent; if it resolves it halfway, the collision comes back. A data-correctness defect that becomes rare is harder to detect, not less harmful. It remains a possible improvement for the day the cache hit ratio is measured, which nobody measures today.

**Accepted cost.** `src/frontend/app.py:87` sends the full history on every turn but the first, so in practice the cache is reserved for the first question of each conversation, which is where it has real value, because it is the one different users repeat.

---

### `BUG-12` 🟠 Concurrent first embeddings hang or crash the process

> After the snapshot: found on 2026-11-10, when the first run of the answer language eval (`BUG-11`) died with a segfault (exit 139) inside the researcher.

**Location.** `src/services/embeddings.py:28` (`embed()`, which runs `model.encode` with `asyncio.to_thread`). Its concurrent callers: the researcher, which embeds its query variants at once (`src/services/agent_graph/nodes.py:85`), and every request the API serves at the same time. Ingestion calls `model.encode` from threads as well (`src/services/ingestion.py:67` and `:170`).

**Analysis.** With torch 2.13.0, sentence-transformers 6.0.1 and CPython 3.14.8 on macOS arm64, several threads entering `model.encode` while the process has not finished a first encode hang or kill the process. Once a single encode has finished, the same concurrency works: four concurrent `embed()` calls after one alone passed 50 of 50 rounds (10 processes, 5 rounds each). **Why the first one matters is not verified**; it looks like a lazy initialization in torch or the tokenizer that is not thread-safe, and it was not chased further, because the fix does not depend on it. `torch.set_num_threads(1)` does not avoid it (2 crashes and 1 hang in 3 runs).

The API usually escapes it because each request embeds alone first (semantic cache or user memory) before the researcher fans out. It does not escape it when a freshly started process gets several requests at once, which is what a restart under traffic looks like. Anything that calls the graph directly, like the eval runner, hits it on its first question.

**Evidence.** Four concurrent `embed()` calls in a new process, with the code of `develop`: 2 segfaults (-11) and 3 hangs (over 60 s) in 5 runs; one call alone works. Against a real uvicorn just started, four simultaneous `/chat/` requests as its first ones (`top_k_rerank=9`, outside the cache):

| Start | Before the fix | After the fix |
|---|---|---|
| 1 | 4 × `ReadTimeout` at 90 s; the process alive and no LLM call made | 4 × 200 in 8–14 s |
| 2 | 4 × `RemoteProtocolError` at 8 s; the server died with exit 133 | 4 × 200 in 8–14 s |

**Patch.** `encode()` in `src/services/embeddings.py`, `model.encode` under one `threading.Lock`; `embed()` and ingestion go through it. It serializes every encode, not just the first ones: whether warm concurrent encodes are safe in every case (a large ingestion batch next to a query, other platforms) was not proven, and the cost is small. One query takes ~7 ms, so the researcher's four variants wait ~20 ms at most. A query that arrives during an ingestion waits for its batch (~1.2 s for 400 sentences, `PERF-03`).

**Status:** ✅ fixed on 2026-11-10. Four concurrent cold `embed()` calls: 0 of 5 → 10 of 10. The API table above, 0 of 2 → 2 of 2 starts. `tests/api/test_concurrent_encode.py` doubles the model with one that records how many calls are inside `encode` at once (a real overlap would hang the suite instead of failing it): the researcher's four queries and an ingestion next to two queries never overlap. Negative control: without the lock, 4 and 2 overlapping calls; with ingestion back on `model.encode`, its sentences never reach the shared encode. The 10 evaluations the verification left in `rag_evaluations` were deleted: 22/128/4/3/0, as before.

---

## 6. Performance

### `PERF-01` 🟠 No connection pool: ~11 connections per query

**Location.** There is not a single `asyncpg.create_pool()` in the repository. The nine data access paths open and close their own connection:

| File:line | Function | Pattern |
|---|---|---|
| `retriever.py:25` | `retrieve_documents` | `connect()` … `finally: close()` |
| `cache.py:21` | `check_semantic_cache` | same |
| `cache.py:49` | `save_semantic_cache` | same |
| `memory.py:48` | `extract_and_save_facts` | same |
| `memory.py:70` | `retrieve_user_facts` | same |
| `graphrag.py:51` | `insert_knowledge_graph` | same |
| `graphrag.py:65` | `retrieve_subgraph` | same |
| `evaluator.py:66` | `evaluate_rag_response` | same |
| `ingestion.py:184` | `insert_documents` | same |

The `try/finally` handling is correct (no connection leaks); the problem is the lack of reuse.

**Cost per query.** Trace of a `knowledge_search` with Multi-Query + HyDE (the normal path):

| Stage | Origin | Connections |
|---|---|:---:|
| `check_semantic_cache` | `chat.py:77` | 1 |
| `retrieve_user_facts` | `chat.py:83` | 1 |
| `retrieve_documents` × 5 | `nodes.py:70` (query + 3 variants + HyDE) | 5 |
| `retrieve_subgraph` | `nodes.py:86` | 1 |
| `save_semantic_cache` | `chat.py:123` | 1 |
| `extract_and_save_facts` | `chat.py:124` (background) | 1 |
| `evaluate_rag_response` | `chat.py:127` (background) | 1 |
| **Total** | | **11** |

With the self-correction loop of `BUG-05`: **17**.

Each connection means a TCP handshake, authentication (`scram-sha-256` by default in PG16), negotiation of session parameters and, on close, a clean shutdown. Locally over loopback it is a few milliseconds; over a real network or a managed database (Cloud SQL, RDS) it is tens.

**Exhaustion risk: the serious problem.** The five retrievals in `nodes.py:70-71` are dispatched with `asyncio.gather`, that is, **they open five simultaneous connections**. The concurrent connection peak scales with `concurrent_users × 5`. With PostgreSQL's default `max_connections` (100):

| Concurrent users | Connection peak | Status |
|:---:|:---:|---|
| 5 | 25 | ✅ |
| 15 | 75 | ⚠️ thin margin |
| 20 | 100 | ❌ `FATAL: sorry, too many clients already` |

Twenty simultaneous users take the system down. And the failure is not graceful: `asyncpg.connect()` raises, the exception climbs up to the `except Exception` in `chat.py:65` and the user gets an opaque `500`.

**Contradiction with the documentation.** `PAPER.md` §5.5 argues:

> *"The total time complexity of this distributed retrieval reduces to $\mathcal{O}(\max_{q_i} T_{retrieval}(q_i))$ thanks to the parallel dispatch of coroutines (`asyncio.gather`), bounded by the latency of the `asyncpg` connection pool."*

The asymptotic bound is correct. The pool that supports it does not exist: today each coroutine also pays the full cost of establishing its own connection, which is precisely the term a pool removes.

**Reproduction.**

```bash
grep -rn "create_pool" src/          # no matches
grep -rn "asyncpg.connect" src/ | wc -l   # 9
```

**Patch.** A global pool initialized in FastAPI's `lifespan`.

`src/api/main.py`:

```python
from contextlib import asynccontextmanager
import asyncpg, os

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        os.getenv("DATABASE_URL"), min_size=5, max_size=20, command_timeout=30,
    )
    yield
    await app.state.pool.close()

app = FastAPI(title="AI Engineer Sandbox API", ..., lifespan=lifespan)
```

Each service goes from `conn = await asyncpg.connect(DB_DSN)` + `finally: close()` to:

```python
async with pool.acquire() as conn:
    ...
```

**Important for the `SEC-02` fix.** With a pool, connections are **reused**, and `SET app.current_tenant` is a session parameter that **persists** on the connection returned to the pool. A connection that served tenant A keeps its `app.current_tenant` when tenant B acquires it. If the next use does not reset it before querying, there is a cross-tenant leak.

Two defenses, apply both:

1. Use `SET LOCAL` inside an explicit transaction, so the value dies with it:
   ```python
   async with pool.acquire() as conn:
       async with conn.transaction():
           await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))
           # true = local to the transaction
   ```
2. Register a `reset` on the pool (`asyncpg.create_pool(..., setup=...)`) that clears the parameter when the connection is returned.

This point is why `PERF-01` and `SEC-02` must be solved in the same change, not separately.

**Status: ✅ fixed (2026-09-15).** There is a new module, `src/services/db.py`, which the nine data access points go through. No `asyncpg.connect` or `SET app.current_tenant` is left in `src/`.

- **A single pool per process** (`get_pool()`), from 5 to 20 connections, configurable with `DB_POOL_MIN_SIZE` and `DB_POOL_MAX_SIZE`. `main.py` warms it up in the `lifespan` (without blocking startup if Postgres is down) and closes it on shutdown.
- **`tenant_connection(tenant_id)`**: takes a connection from the pool, opens a transaction and sets the tenant as a parameter with `set_config('app.current_tenant', $1, true)`. It is also the defense in depth pending from `SEC-02`.
- **Embeddings are computed before taking a connection** in `retriever.py`, `cache.py` and `memory.py`. Before, the connection was opened and then the CPU work was done, with the connection held unused.

Adjustments to the patch above:

- **The pool is created on demand and tied to the event loop**, not only in the `lifespan`, because the ingestion CLI and the scripts use it too. The CLI closes it when it finishes.
- **Only defense 1 was needed.** asyncpg already provides defense 2: since 0.30 it runs `RESET ALL` when returning each connection to the pool (`Connection.get_reset_query`). It was measured with a session-level tenant, as the old code did, on a single-connection pool. With the default reset, the next request does not see the tenant (0 rows). With an empty reset, **it does**: 128 foreign triples. The transaction-local `set_config` does not depend on that behavior.
- **Found on the way.** `ingestion.py` had the `postgres` superuser's DSN as its default. If `DATABASE_URL` was missing, ingestion bypassed RLS. With a single DSN, the default becomes `app_user`.

Verified against real Postgres. The old code is the exact copies from HEAD (`ea88100`) of the six services, run in the same process as the new ones. The "read path" is the reads of a `knowledge_search`: cache, memory, the 5 parallel searches and the graph.

| Measure | Before | After |
|---|:---:|:---:|
| New connections per query (`pg_stat_database.sessions`, 10 queries) | **8** | **0** |
| Median of the read path | 206 ms | **76 ms** |
| 25 concurrent queries: `app_user` connection peak | 95 of 97 available | **13** |
| Same: errors | **7 `TooManyConnectionsError`** | **0** |
| Same: total duration | 3.6 s | 1.7 s |

The Postgres log records, at the moment of the old code's burst, dozens of `FATAL: sorry, too many clients already`.

Isolation, with the pool forced to 2 connections to make them be reused across tenants:
- 200 interleaved operations from two tenants and 60 concurrent `retrieve_subgraph` calls: all of them see only their own data.
- A connection just returned to the pool does not keep the previous tenant (20 of 20).
- With both tenants, the cache, memory, the 5 searches and the graph return the same as at HEAD.

Real application (uvicorn, LLM and Postgres):
- Streaming chat (141 events), ingestion through the API and background tasks, without opening **a single** new connection on the server.
- Ingestion through the CLI with the pool created on demand.
- Everything under the right tenant, and the database returned to its initial state.

**Limits.** The latency gain is that of the database path locally, over loopback; the total time of a question is still dominated by the LLM and the re-ranking. Closing the pool in the CLI is hygiene: without that close no warning appeared, not even with `python -X dev`, and no `unexpected EOF` on the server.

---

### `PERF-02` 🟠 Four copies of the embedding model in RAM

**Location.** `SentenceTransformer("all-MiniLM-L6-v2")` is instantiated at module level, independently, in four files:

| File:line | Context |
|---|---|
| `src/services/retriever.py:17` | preceded by `print("Cargando modelo local de embedding...")` |
| `src/services/cache.py:14` | preceded by the comment that acknowledges the problem |
| `src/services/memory.py:13` | no comment |
| `src/services/ingestion.py:24` | preceded by `print("Cargando modelo local...")` |

The code itself documents it in `cache.py:13`:

```python
# Reutilizar el mismo modelo en memoria (debería idealmente instanciarse 1 sola vez por app)
model = SentenceTransformer(EMBEDDING_MODEL)
```

("Reuse the same model in memory (ideally it should be instantiated only once per app)".)

**Analysis.** Being module-level instantiations, they run at `import` time. Since the four modules are imported in the chain that starts from `src/api/main.py`, the FastAPI process loads **four full instances** of the model.

`all-MiniLM-L6-v2` is ~90 MB on disk; in memory, with float32 weights plus the tokenizer and the PyTorch graph, it is around 90–120 MB per instance. The overhead is about 270–360 MB of unnecessary memory.

**The real impact is the cold start.** Each instantiation means reading the weights from disk, deserializing them and initializing the PyTorch backend. Four times, sequentially, on the import path.

This ties directly to a problem already documented. `TROUBLESHOOTING.md` §3 diagnoses:

> *"With Uvicorn running with the `--reload` flag, any file edit restarted the server on the fly. During those 10 seconds, Uvicorn loads the heavy machine learning models (`SentenceTransformers` and `FlashRank`) into RAM. A request made in that exact window was refused."*

Those "10 seconds" are largely the four redundant loads. The post-mortem treated the symptom (killing zombie processes, explaining the latency to the user) without noticing that the load was **fourfold**. Consolidating cuts that window to roughly a quarter.

**Contrast with the reranker.** `reranker.py:10` instantiates `Ranker` only once and every consumer shares it through the import. It is the right pattern, already present in the repository.

**Reproduction.**

```bash
grep -rn "SentenceTransformer(" src/
# retriever.py:17, cache.py:14, memory.py:13, ingestion.py:24
```

**Patch.** A shared module, `src/services/embeddings.py`:

```python
"""Single instance of the embedding model, shared by the whole process."""
from functools import lru_cache
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384   # must match vector(384) in sql/01_init.sql


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    print(f"Loading local embedding model {EMBEDDING_MODEL} (only once)...")
    return SentenceTransformer(EMBEDDING_MODEL)


def to_pgvector(embedding) -> str:
    """Serializes an embedding to the literal pgvector expects."""
    return f"[{','.join(str(x) for x in embedding.tolist())}]"
```

The four consumers move to `from src.services.embeddings import get_model, to_pgvector`.

`to_pgvector` removes another duplication on the way: the expression

```python
emb_str = f"[{','.join(str(x) for x in query_embedding.tolist())}]"
```

is repeated **seven times** literally (`retriever.py:28`, `cache.py:26`, `cache.py:54`, `memory.py:54`, `memory.py:75`, `ingestion.py:194`, and in `test_sim.py`). Centralizing `EMBEDDING_DIM` also documents the coupling with the schema's `vector(384)`, implicit today.

**Status: ✅ fixed (2026-09-15).** There is a new module, `src/services/embeddings.py`, with the single instance of the model, `embed()` (the embedding in a thread) and `to_pgvector()`. `retriever.py`, `cache.py`, `memory.py` and `ingestion.py` no longer instantiate the model or repeat the pgvector conversion. Three differences from the patch above:

- **It loads at import time, not on the first call.** It is the same pattern as the `Ranker`. With `lru_cache`, the first request would pay several seconds of loading, and the cache does not protect against two threads at once: several simultaneous calls from `asyncio.to_thread` could load the model twice.
- **`to_pgvector()` accepts a numpy array or a list**, because `ingestion.py` stores the embedding already converted to a list.
- **At import time it checks that the model produces 384 dimensions.** That way, a model change fails at startup, with a message pointing to the schema, instead of failing on the first `INSERT`.

`chunk_text` still calls `model.encode` on the event loop thread; that is `PERF-03`.

Verified by importing the real application (`src.api.main`) in a clean process. The old code ran from a worktree of the previous commit (`986e03e`), with the disk cache already warm for both variants:

| Measure | Before | After |
|---|:---:|:---:|
| Live `SentenceTransformer` instances | 4 | **1** |
| Nominal parameter memory | 363.6 MB (4 × 90.9) | **90.9 MB** |
| Import of `src.api.main` | 16.6 s | **5.6 s** |
| Process *physical footprint* after importing (3 measurements per variant) | 1350–1351 MB | **1248–1249 MB** |

Equivalence and functional checks:
- **Same results** (12 entries) as the old code: searches for both tenants, cache, memory, the semantic chunking of a text and the hash of its embeddings.
- **The real application loads the model only once.** Streaming chat, ingestion through the API and through the CLI work with no errors and no new connections, and the database is left in its initial state.

**Correction to the estimate above.** The measured memory saving is **~102 MB** of *physical footprint*, stable across the six measurements, not 270–360 MB. The copies were independent: four different weight addresses, without file-backed storage. Why the footprint drops less than the nominal memory (272 MB) remains **unexplained**. macOS RSS is no use for measuring it: it swung between 197 and 274 MB on identical runs. What is confirmed is the other half of the analysis: the cold start. Importing the API goes from 16.6 s to 5.6 s, which is a good part of the window in `TROUBLESHOOTING.md` §3.

---

### `PERF-03` 🟡 `model.encode` blocks the event loop during ingestion

**Location.** `src/services/ingestion.py:72`, inside `chunk_text()`:

```python
sentence_embeddings = model.encode(sentences)
```

**Analysis.** `chunk_text` is a **synchronous** function (`def`, not `async def`, l. 48) that runs PyTorch inference on CPU. It is called from two points on the asynchronous path:

- `ingestion.py:220`: `ingest_file` for `.md` / `.txt`
- `ingestion.py:143`: `process_pdf`, once **per page** of the PDF

Since it is not dispatched to a thread, the inference runs on the event loop thread and blocks it completely.

**Contrast within the same file.** The repository uses `asyncio.to_thread` correctly at the other points where it calls `model.encode`:

| Location | Pattern |
|---|---|
| `retriever.py:27` | ✅ `await asyncio.to_thread(model.encode, query)` |
| `cache.py:25` | ✅ `await asyncio.to_thread(...)` |
| `cache.py:53` | ✅ `await asyncio.to_thread(...)` |
| `memory.py:53` | ✅ `await asyncio.to_thread(...)` |
| `memory.py:74` | ✅ `await asyncio.to_thread(...)` |
| `ingestion.py:172` | ✅ `await asyncio.to_thread(model.encode, texts)` (in `generate_embeddings`) |
| **`ingestion.py:72`** | ❌ **direct call** |

It is the only exception: an oversight, not a decision.

**Impact.** While ingesting a 20-page PDF with ~40 sentences per page, `model.encode` is called 20 times on batches of 40 sentences. During each one, the server **stops answering every request**: ongoing chats, open SSE streams and `/health` itself. A load balancer with aggressive healthchecks could mark the instance as down during a large ingestion.

Note that `generate_embeddings` (l. 168-175) does dispatch correctly: the blocking happens earlier, in the chunking phase.

**Reproduction.**

```bash
grep -n "model.encode" src/services/ingestion.py
# 72:    sentence_embeddings = model.encode(sentences)      ← without to_thread
# 172:   embeddings_np = await asyncio.to_thread(model.encode, texts)
```

**Patch.** Dispatch the whole function, which is the CPU-bound unit of work:

```diff
--- a/src/services/ingestion.py
@@ async def process_pdf(file_path: str) -> List[DocumentChunk]:
         if text.strip():
-            page_chunks = chunk_text(text, source_type=f"pdf_page_{page_num+1}")
+            page_chunks = await asyncio.to_thread(chunk_text, text, f"pdf_page_{page_num+1}")
             chunks.extend(page_chunks)
@@ async def ingest_file(file_path: str, tenant_id: str) -> IngestionResult:
-        chunks = chunk_text(content, source_type="markdown")
+        chunks = await asyncio.to_thread(chunk_text, content, "markdown")
```

**A related note, same cause.** The three tools in `src/services/tools.py` use `requests` (synchronous) and are called from `supervisor_node`, which is `async` (`nodes.py:40`: `tool_result = tool_func(**intent.tool_args)`). Each call to CoinGecko or GitHub blocks the event loop for up to the 5-second timeout. The fix is the same (`await asyncio.to_thread(tool_func, **intent.tool_args)`), or migrating `tools.py` to `httpx.AsyncClient`, which is already in the dependency tree as a transitive dependency of `anthropic`.

**Status: ✅ fixed (2026-09-15).** Three changes:

- **`chunk_text` is dispatched whole with `asyncio.to_thread`** in both of its calls: `ingest_file` (text and markdown) and `process_pdf` (each page).
- **So are the supervisor's tools**, with `await asyncio.to_thread(tool_func, **intent.tool_args)`. Migrating `tools.py` to `httpx.AsyncClient` was ruled out because it would change the tools' interface for what one line solves. The trade-off: a slow tool holds a thread of the default executor, which it shares with the embeddings, until its 5 s timeout.
- **The `chunk_text` comment is corrected**, which claimed that the embedding *"is instant locally"*: it took between 0.6 and 1.2 s with 400 sentences.

Verified against the real server. During each scenario, a client polls `/health` every 20 ms, and what is measured is the longest it waits. In ingestion only the DB insert and the GraphRAG extraction were replaced, since they play no part in the blocking; chunking and embeddings are the real ones. The tools were wrapped only to record their duration.

| Scenario | Synchronous work | `/health` max before | `/health` max after |
|---|---|:---:|:---:|
| Idle | — | 17.6 ms | 13.2 ms |
| Ingesting a `.txt` of 400 sentences (58 chunks) | `chunk_text`: 1151 ms / 604 ms | **1182 ms** | **21 ms** |
| Chat with `get_crypto_price` (real CoinGecko) | tool: 178 ms / 129 ms | **204 ms** | **13.6 ms** |

Before, the `/health` wait matched the duration of the synchronous work: the server served nothing else. The same 58 chunks come out, the tool returns the price and the database is left in its initial state. The difference in `chunk_text`'s duration between runs is not due to the change: the thread does not speed up the computation, it only stops it from freezing the server.

**PDF path**, measured separately, without DB or LLM, with a 5 ms heartbeat in the same process: a 20-page PDF with 80 sentences each, processed by the previous version (`17c1862`) and by the new one.

| | Before | After |
|---|:---:|:---:|
| Maximum event loop stall | **1060 ms** | **16 ms** |
| `process_pdf` duration | 1.05 s | 1.00 s |
| Chunks | 217 | 217, identical |

**A refinement of the analysis above.** With a text-only PDF there is not one block per page, but **a single one that lasts the whole processing**: 1060 ms of stall in 1.05 s. `process_pdf` has no `await` between pages when there are no images, so it did not hand control back to the event loop until it finished. `fitz.open`/`get_text` and the file reads in `ingest_file` are still synchronous and stay as they are; in this measurement they take milliseconds.

---

### `PERF-04` 🟡 `max_tokens=300` truncates the evaluator

**Location.** `src/services/evaluator.py:58-63`

```python
evaluation = await client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=300,
    messages=[{"role": "user", "content": prompt}],
    response_model=RAGEvaluation,
)
```

**Analysis.** The 300-token budget must cover the tool-calling envelope Instructor generates, three floats, and the `reasoning` field, which is free text with no declared limit:

```python
reasoning: str = Field(..., description="Breve explicación de las puntuaciones otorgadas.")
```

("A brief explanation of the scores given.") "Brief" is an instruction in natural language, not a constraint. Nothing stops the model from writing a 400-token paragraph justifying the three metrics.

**Failure mode.** When the generation reaches `max_tokens`, the answer is cut off mid-JSON. Instructor cannot parse it, raises, and the `except Exception` on line 86 swallows it:

```python
except Exception as e:
    print(f"⚠️ [Evaluator] Error durante la evaluación: {e}")
```

The evaluation is lost. No row is left in `rag_evaluations`, there is no metric, no alert. Just a line on stdout nobody reads in production.

**A pattern already diagnosed.** `TROUBLESHOOTING.md` §6 documents exactly this failure in the extractor:

> *"`max_tokens` was raised from 1024 to 2048 so the output is not cut off by the limit and breaks the validation of the final JSON."*

The extractor is at 8192 today (`extractor.py:43` and `:78`). The evaluator stayed at 300 and did not get the same treatment.

**Resulting statistical bias.** The truncation is not random: it is more likely to hit evaluations with longer reasoning, which are typically those of problematic cases (answers with partial hallucinations, ambiguous context). That is, **the evaluations that matter most are the ones lost most**, and the aggregated metrics are biased upwards. This directly compromises epic 2 of `ROADMAP_PHASE_5_SCALABILITY.md` (the evaluations dashboard): the time series would be built on a biased sample.

**Reproduction.**

```bash
grep -n "max_tokens" src/services/*.py
# evaluator.py:60  → 300      ← the lowest with a free-text field
# memory.py:38     → 200      (only a list of short strings; acceptable)
# router.py:76     → 500
# graphrag.py:37   → 1024
# ingestion.py:119 → 1000
# extractor.py:43  → 8192
# extractor.py:78  → 8192
```

**Patch.** Widen the budget and bound the field in the schema:

```diff
--- a/src/services/evaluator.py
     reasoning: str = Field(
         ...,
-        description="Breve explicación de las puntuaciones otorgadas."
+        description="Concise explanation of the scores, at most 3 sentences.",
+        max_length=600,
     )
@@
-        max_tokens=300,
+        max_tokens=1024,
```

Combine it with the `DOC-02` patch (adding `ge`/`le` to the three scores), which fixes the module's other silent failure mode.

**A cross-cutting recommendation.** Three subsystems swallow exceptions without leaving a structured trace: `evaluator.py:86`, `memory.py:63` and `graphrag.py:42`. All three are background or best-effort, so they must not propagate, but they should log with the `logging` module and a counter metric, not with `print`. Today, if the evaluator stopped working altogether, nothing would show it except the absence of new rows in a table nobody queries.

**Measured observation (2026-09-14).** Starting the server with unbuffered stdout showed the error the `print` on line 86 made invisible: *"The output is incomplete due to a max_tokens length limit"*. The diagnosis is confirmed, but the failure is **intermittent**, not systematic. It depends on how long the judge's answer turns out, not on the size of the corpus:

| Verification | Judge's context | Result |
|---|---|---|
| `BUG-02` | 10 documents from the real corpus | Failed on `max_tokens` |
| `BUG-04` | 1 document (new database) | Stored the evaluation |
| `BUG-06`, `BUG-05` | Up to 10 documents from the real corpus | Stored evaluations in several runs |

The development database has no evaluations. The message of commit `1a35a4d` (`BUG-02`) claims the evaluator always fails; it is wrong. For testing, a row may appear in `rag_evaluations` after answering, and that has to be accounted for.

**Status: ✅ fixed (2026-09-15)**, together with `DOC-02`, as the patch recommends. Changes in `evaluator.py`:

- `max_tokens` goes from 300 to 1024.
- `reasoning` is bounded with `max_length=600` and a description that asks for at most three sentences.
- Explicit `max_retries=3`. Instructor 1.16 already made 3 attempts by default in `AsyncInstructor.create`, which is what `from_anthropic` returns; it is pinned so as not to depend on what another version ships.

Verified with the real judge (Claude Haiku). 5 corpus questions were taken, with 10 retrieved and re-ranked context documents and the generator's real answer, produced once and shared. Each question was evaluated 3 times with the previous evaluator (`17c1862`) and 3 with the new one, alternating:

| | Before | After |
|---|:---:|:---:|
| Evaluations stored | 5/15 | **15/15** |
| Lost to truncation (`max_tokens`) | **10/15** | 0 |
| Stored `reasoning` (median / maximum) | 746 / 785 characters | 438 / 564 characters |

All the new scores are in [0, 1], and the database was returned to its initial state.

**A refinement of the observation above.** With a realistic context of 10 documents, the loss was not occasional: it affected **two of every three** evaluations. The few that were stored carried reasoning of up to 785 characters, at the edge of what fit in 300 tokens together with the JSON.

The cross-cutting recommendation is not applied: logging with `logging` instead of `print` in `evaluator.py`, `memory.py` and `graphrag.py`.

---

## 7. Divergences between Documentation and Code

This is the most relevant category for a portfolio repository: these are claims **anyone can verify** by opening the code next to the paper.

### `DOC-01` 🟠 Token-by-token streaming no longer exists

**What the documentation says.**

`README.md` §3, as a highlighted state-of-the-art feature:

> *"SSE streaming + Pydantic v2: structured generation of partial answers in real time over Server-Sent Events using the `Instructor` library. It guarantees deterministic JSON without syntax hallucinations."*

`TROUBLESHOOTING.md` devotes **two full post-mortems** to it: §4 (*"The Streamlit frontend freezes while streaming (SSE)"*, with the backpressure analysis and the solution through `st.write_stream()`) and §5 (*"Type error from partial objects"*, about `instructor.Partial` emitting `{"answer": null}`).

`PAPER.md` §4.4 formalizes it in the presentation layer.

**What the code does.**

`generate_answer_stream()` (`src/services/extractor.py:56-90`) implements real streaming (`Partial[StructuredAnswer]`, `stream=True`, incremental emission per token):

```python
response = await client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=8192,
    messages=[{"role": "user", "content": prompt}],
    response_model=Partial[StructuredAnswer],
    stream=True
)
async for partial_model in response:
    yield partial_model.model_dump_json() + "\n"
```

and **it is not called from anywhere in the repository**. It was orphaned in the migration to LangGraph: `generator_node` (`nodes.py:107`) calls `generate_answer`, the non-streaming version.

What `/chat/stream/` emits today (`chat.py:102-120`) is **four discrete SSE events**:

| # | When | Content |
|:---:|---|---|
| 1 | after `supervisor` | `"🤖 *Supervisor evaluando estrategia...*"` |
| 2 | after `researcher` | `+ "🔍 *Investigador buscando en Postgres Vector y GraphRAG...*"` |
| 3 | on entering `generator` | `+ "✍️ *Redactor estructurando respuesta final...*"` |
| 4 | after `generator` | `+ ` **the full answer at once** |

**Impact.** It is *progress streaming*, not *token streaming*. The live typing effect (the "familiar ChatGPT-style effect" `TROUBLESHOOTING.md` §4 describes) was lost: the user sees three status lines appear quickly and then a full block of text all at once, after several seconds of waiting.

The frontend is still prepared for the former: `stream_parser()` (`app.py:100-124`) computes character diffs between consecutive events, logic designed for hundreds of incremental events that now receives four. It works, but adds nothing.

**A note on `astream`.** The code uses `agent_graph.astream(initial_state)` (`chat.py:102`), which emits **one update per completed node**, not per token. Real token streaming through LangGraph needs `astream_events(..., version="v2")` and filtering the `on_chat_model_stream` events. The choice of `astream` is consistent with what the code does; it is just not what the documentation describes.

**Reproduction.**

```bash
grep -rn "generate_answer_stream" src/
# only match: src/services/extractor.py:56 (the definition)

grep -n "astream\|astream_events" src/api/routers/chat.py
# 102: async for output in agent_graph.astream(initial_state):
```

**Fix.** Two paths, and one has to be chosen explicitly:

**(a) Bring the feature back.** Move to `astream_events` and pass the generator's tokens along:

```python
async for event in agent_graph.astream_events(initial_state, version="v2"):
    kind = event["event"]
    if kind == "on_chain_start" and event["name"] in ("supervisor", "researcher"):
        yield f"data: {json.dumps({'answer': progress, 'sources': []})}\n\n"
    elif kind == "on_chat_model_stream":
        # incremental fragment from the generator
        ...
```

It requires `generator_node` to call `generate_answer_stream` and LangGraph to propagate the async generator: real work, not trivial.

**(b) Align the documentation with reality.** Delete `generate_answer_stream` (dead code), rewrite the README feature as *"Per-node progress streaming over SSE"* (which is honest and still a good feature) and add a note to `TROUBLESHOOTING.md` §4-5 saying that they describe the Phase 3 implementation, replaced in Phase 4.

Either is acceptable. What is not acceptable is the current state: an advertised feature with a dead function in the tree.

**Status: ✅ fixed (2026-09-13) through path (a).** Token-by-token streaming was brought back.

**Correction to the proposed path.** The sketch of (a) would not have worked: `astream_events` emits `on_chat_model_stream` only for LangChain *chat models*, and this project calls the Anthropic SDK directly through `instructor`. Down that path not a single token would have arrived. The right mechanism for this architecture is the graph's `custom` channel: `generator_node` gets a `get_stream_writer()` and writes the fragments as it receives them; `/chat/stream/` consumes `astream(stream_mode=["updates", "custom"])`, which yields `(mode, chunk)` tuples with the `custom` ones interleaved before the node's `updates`. Outside a streaming context (the `ainvoke` of `/chat/`) the writer is a no-op, so the non-streaming endpoint is unaffected.

`generate_answer_stream` stops being dead code and changes its contract: it emits the partial model instead of its serialized JSON, because the node needs the incremental text for SSE and the final object for the state. In addition, both generators now share `_build_prompt()`: having two copies of the prompt is exactly why the anti-plain-text instruction from [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) §6 lived only in the dead version (see Appendix D).

**Measured against a real server** (not with `TestClient`, which buffers the whole response and gives identical timestamps for every event), same question:

| | SSE events | Generator's 1st text | Full answer |
|---|:---:|:---:|:---:|
| Before | 4 | 13.49 s (the whole block at once) | 13.91 s |
| After | 244 | 9.55 s | 12.51 s |

The text starts about 4 seconds earlier and the last ~3 seconds are live typing. The improvement should not be overstated: most of the latency is not in generation but in retrieval and re-ranking, so the user still waits about 9 seconds before seeing the first letter. Cutting that part is a job for `PERF-01` and `PERF-02`.

**Two details that had to be solved.** The self-correction loop (`BUG-05`) can go through the generator twice, and `stream_parser()` (`app.py:118`) only renders when the text grows: a second draft that shrank the string would desynchronize the UI. That is why the retry is announced and chained instead of replacing. And since every field in `Partial` is optional, a partial that never completes the schema (generation truncated by `max_tokens`, cut off mid-answer) is not filled in by hand: it falls back to `generate_answer` and its answer is chained.

The frontend was not touched: `stream_parser()` was written for this and until now received four events where it expected hundreds. Also verified that what is stored in the cache and sent to the evaluator is still free of the progress messages (`BUG-01`), that the greeting, the tools and the non-streaming endpoint still work, and that coreference resolution (`BUG-03`) still works on the streaming path.

---

### `DOC-02` 🟠 The paper claims Pydantic validations that do not exist

**What the documentation says.** `PAPER.md` §5.6 (in both the Spanish and the English paper):

> *"The Pydantic constraints `ge=0.0` and `le=1.0` forcibly reject any LLM response outside the probabilistic support, raising a `ValidationError` that guarantees the stability of the audit metric system."*

**What the code does.** `RAGEvaluation` (`src/services/evaluator.py:14-30`) declares the three scores **without any range constraint**:

```python
class RAGEvaluation(BaseModel):
    faithfulness_score: float = Field(
        ...,
        description="Puntuación de 0.0 a 1.0 indicando si la respuesta es fiel al contexto (sin alucinaciones)."
    )
    relevance_score: float = Field(...)          # no ge/le
    context_precision_score: float = Field(...)  # no ge/le
```

The range is a **natural language description**, not a constraint. Pydantic accepts `1.7`, `-0.3` or `42.0` without objection.

**Where the confusion comes from.** `StructuredAnswer.confidence_score` (`src/models/structured.py:11`) **does** have them:

```python
confidence_score: float = Field(..., description="Nivel de confianza...", ge=0.0, le=1.0)
```

The paper describes the project's pattern correctly, but attributes it to the wrong module.

**The real failure chain.** The only effective defense is in SQL (`sql/01_init.sql:64-66`):

```sql
faithfulness_score FLOAT CHECK (faithfulness_score >= 0.0 AND faithfulness_score <= 1.0),
```

If the judge returns `1.2`:

1. Pydantic validates → ✅ passes.
2. The `INSERT` violates the `CHECK` → `asyncpg.exceptions.CheckViolationError`.
3. The `except Exception` in `evaluator.py:86` swallows it with a `print`.
4. **The evaluation is silently lost.**

It is exactly the failure the paper claims is prevented. And it is the module's second silent loss path, next to `PERF-04`.

**Why it is likely.** LLMs return out-of-range values in scoring tasks more often than expected, especially at the default temperature (1.0, according to `PAPER_PLAN.md` §3.4): they confuse 0–1 scales with 0–10, or round to `1.0000001`.

**Reproduction.**

```bash
grep -n "ge=\|le=" src/services/evaluator.py    # no matches
grep -n "ge=\|le=" src/models/structured.py     # 11: ge=0.0, le=1.0
```

**Patch.** It aligns the code with what the paper already claims; there is no need to touch the paper:

```diff
--- a/src/services/evaluator.py
 class RAGEvaluation(BaseModel):
     faithfulness_score: float = Field(
-        ...,
+        ..., ge=0.0, le=1.0,
         description="Puntuación de 0.0 a 1.0 indicando si la respuesta es fiel al contexto (sin alucinaciones)."
     )
     relevance_score: float = Field(
-        ...,
+        ..., ge=0.0, le=1.0,
         description="Puntuación de 0.0 a 1.0 indicando si la respuesta responde directamente a la pregunta."
     )
     context_precision_score: float = Field(
-        ...,
+        ..., ge=0.0, le=1.0,
         description="Puntuación de 0.0 a 1.0 indicando si el contexto provisto contenía la información necesaria o si había basura irrelevante."
     )
```

With this, Instructor catches the `ValidationError` and **retries by feeding the error back to the model** (the self-correction behavior `ARCHITECTURE.md` §4 describes for the extractor) instead of losing the record. The SQL `CHECK` becomes the second line of defense it was meant to be.

**Status: ✅ fixed (2026-09-15)**, in the same change as `PERF-04`. The three `RAGEvaluation` scores carry `ge=0.0, le=1.0`. The code now does what `PAPER.md` §5.6 claims, so the paper needs no changes.

Verified without an LLM, with `faithfulness_score=1.2`:
- **Before:** the schema accepts it, and the real `INSERT` into `rag_evaluations` fails on the `CHECK`. It is the silent loss path described above.
- **After:** the schema rejects it with `ValidationError` before it reaches SQL, where Instructor can retry.

In the 15 real evaluations of the `PERF-04` verification no out-of-range score appeared, so the range retry was not observed in practice.

---

### `DOC-03` 🟠 `.env.example` does not allow the project to start

**What the documentation says.** `README.md` §"How to run", step 3:

> *"Configure the credentials: copy the `.env.example` file to `.env` and add your `ANTHROPIC_API_KEY`."*

`PAPER_PLAN.md` §1 describes it as: *"Environment variable template (Anthropic API keys and the JWT secret)"*.

**What the file contains.**

```bash
# Base de datos
DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5433/postgres

# OpenAI
OPENAI_API_KEY=tu_clave_de_openai_aqui

# Langfuse
LANGFUSE_SECRET_KEY=tu_secret_key_de_langfuse
LANGFUSE_PUBLIC_KEY=tu_public_key_de_langfuse
LANGFUSE_HOST=https://cloud.langfuse.com
```

**Three problems.**

1. **There is no `ANTHROPIC_API_KEY`.** The README says "add your `ANTHROPIC_API_KEY`", but the template has no entry for it. The seven LLM calls read `os.getenv("ANTHROPIC_API_KEY")` and would get `None`.

2. **There is an `OPENAI_API_KEY`, which is used nowhere.** It is a leftover from Phase 1. It comes from `CONTEXT.md`, which still describes the whole stack with OpenAI:
   > *"Clients & models: OpenAI (`gpt-4o-mini`, `text-embedding-3-small`), `Instructor`."*
   
   That document also freezes the "current status" at Phase 1 (only `extractor.py`, `retriever.py`, `reranker.py`) and does not mention Anthropic, LangGraph, GraphRAG, memory or the evaluator.

3. **There is no `JWT_SECRET_KEY`**, because it does not exist (`SEC-01`). `PAPER_PLAN.md` claims the template includes it; that is not true.

**A fourth problem, the most serious: the example DSN switches RLS off.**

The template points to `postgresql://postgres:...`, the **superuser that owns** the tables. But `sql/create_app_user.sql` exists precisely to create a different role:

```sql
CREATE USER app_user WITH PASSWORD 'apppassword';
```

The reason is that in PostgreSQL **a table's owner bypasses its own RLS policies** unless `FORCE ROW LEVEL SECURITY` is declared. And `01_init.sql` declares `FORCE` on none of its four tables (`BUG-04`).

The consequence: whoever follows the README literally starts the system with multi-tenant isolation **switched off in practice** on `documents`, `semantic_cache`, `user_memory` and `rag_evaluations`, while the README, the paper and `GRAPHRAG_ARCHITECTURE.md` say it is active. Every query would see every row of every tenant.

The code's defaults do point to the right user (`retriever.py:13`, `cache.py:10`, `memory.py:11`, `graphrag.py:11`, `evaluator.py:10` use `app_user`), with one exception: `ingestion.py:21` falls back to `postgres` by default. A minor inconsistency, but in the same direction.

**Reproduction.**

```bash
cat .env.example
grep -rn "ANTHROPIC_API_KEY" .env.example        # no matches
grep -rn "OPENAI" src/                            # no matches
grep -rn 'DB_DSN = os.getenv' src/services/ | grep -c app_user   # 5 of 6
```

**Patch.** Rewrite `.env.example`:

```bash
# --- Database ---
# IMPORTANT: use app_user, not postgres. The tables' owner bypasses the RLS
# policies unless FORCE ROW LEVEL SECURITY (see sql/create_app_user.sql).
DATABASE_URL=postgresql://app_user:apppassword@localhost:5433/postgres

# --- Anthropic (Claude) ---
ANTHROPIC_API_KEY=sk-ant-...

# --- Authentication ---
# Generate with: openssl rand -hex 32
JWT_SECRET_KEY=change_this_to_a_random_key

# --- Observability (optional) ---
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

Align `ingestion.py:21` to the same default, and add a historical-document header to `CONTEXT.md` (or rewrite it with the real stack).

**Status:** ✅ fixed on 2026-09-16.

**What was still open.** Part of the finding had been solved along the way: `JWT_SECRET_KEY` entered the template with `SEC-01`, `FORCE ROW LEVEL SECURITY` with `BUG-04` and the `ingestion.py` default with `PERF-01`. Still open were the missing `ANTHROPIC_API_KEY`, the unused `OPENAI_API_KEY` and the superuser DSN. And there was a new problem, **introduced by `SEC-05`**: the README ordered `docker compose up -d` (step 2) before creating `.env` (step 3), but since `SEC-05` Compose requires `TENANT_SIGNING_KEY` to interpolate the service.

**Verification: startup from a clean clone** of `HEAD`, following only the instructions, in a separate Compose project. Declared deviations: the repository's `.venv` was reused instead of `uv sync` (the dependencies are `HYG-01`), and other ports were used because the development ones were taken; `DATABASE_URL` was changed only in the port.

| Step | Previous files | Fixed files |
|---|---|---|
| Start the database | Fails: `required variable TENANT_SIGNING_KEY is missing a value`, before and after copying `.env` | Starts (the README asks to fill in `.env` first) |
| `ANTHROPIC_API_KEY` in the template | Missing; the line has to be added by hand | Present, marked as required |
| Start the API with what the README asks for | Fails: `RuntimeError: JWT_SECRET_KEY is not set` | Starts |
| Role the API connects as | `postgres` (superuser) | `app_user` |

**Isolation, end to end.** In each arm, `bryan` (tenant 0000) ingested through the API a document with an impossible-to-guess fact (a made-up city), and `company_x` (tenant 1111) asked about it. `top_k_rerank=9`, so that no request touched the cache.

| | Previous files | Fixed files |
|---|---|---|
| `company_x` (another tenant) | **Gets the fact**, with 2 sources | Does not: 0 sources, empty context |
| `bryan` (positive control) | Gets it | Gets it |
| `documents` rows `company_x`'s connection sees | 1, from another tenant | 0 |

With the previous template, one tenant read another's documents end to end, despite `FORCE`, the `SEC-05` signature and everything else: a superuser does not go through the policies. The positive control rules out that the fixed template's result is a retrieval failure.

A first attempt asked about an "access code". The supervisor refused to search for it because it looked like a credential (0 sources and *"No puedo proporcionar códigos de acceso…"*, "I can't provide access codes…"), so that result said nothing about isolation and it was repeated with a harmless fact.

**Changes.** `.env.example` rewritten: `app_user` in `DATABASE_URL`, with the reason; `ANTHROPIC_API_KEY` required; no `OPENAI_API_KEY`; and Langfuse empty and optional (checked: the application works the same without its keys). In the README, filling in `.env` becomes step 2, before starting the database, with the commands to generate the two keys. `CONTEXT.md` gets a historical-document header.

**Out of scope.** `scratch_db.py` and `test_db.py`, in the root, still connect as `postgres`. They are the dead code of `HYG-02`: the application does not use them and the documentation does not cite them.

---

### `DOC-04` 🟡 `NetworkX` documented but never used

**What `README.md` §2 says:**

> *"GraphRAG (knowledge graphs): dynamic extraction of entities and relations (**NetworkX**) stored in Postgres."*

**What the code does.** `src/services/graphrag.py` (99 lines) is only:
- a call to Claude through Instructor to extract triples (`extract_knowledge_graph`),
- two SQL queries (`insert_knowledge_graph`, `retrieve_subgraph`).

There is no in-memory graph structure, no topological algorithm, no `networkx` import anywhere in the repository. The package is not declared in `pyproject.toml`; it exists in the environment only as a transitive dependency.

**Contrast with the roadmap.** `ROADMAP_PHASE_5_SCALABILITY.md` §5 presents it **correctly as future work**:

> *"Implement the `NetworkX` library or migrate the data to a native graph engine such as Neo4j / Apache Age. Compute PageRank, community detection (Leiden) or betweenness centrality algorithms."*

The roadmap is honest; the README presents as implemented what the roadmap describes as pending.

`PAPER.md` §5.5 is honest too: it describes the engine as *"naive"*, with *"flat 1-hop relational interpolation"*.

**Reproduction.**

```bash
grep -rn "networkx\|import nx" src/ tests/     # no matches
grep -n "networkx" pyproject.toml              # no matches
```

**Patch.** In `README.md`, remove the false attribution:

```diff
-*   **GraphRAG (knowledge graphs):** dynamic extraction of entities and relations (NetworkX) stored in Postgres. When querying, subgraphs are retrieved to understand the big picture.
+*   **GraphRAG (knowledge graphs):** extraction of triples (entity–relation–entity) with an LLM, stored in PostgreSQL under RLS. When querying, a 1-hop subgraph is retrieved and injected into the context without going through the re-ranker. (Topological analysis, such as PageRank and centrality, is planned in [Phase 5](docs/history/ROADMAP_PHASE_5_SCALABILITY.md).)
```

---

### `DOC-05` 🟡 `ARCHITECTURE.md` frozen at Phase 1

**Analysis.** The document describes an architecture that no longer exists, **with no note saying it is historical**. Its name (`ARCHITECTURE.md`, in the root) invites reading it as the primary reference.

| `ARCHITECTURE.md` claims | Location | Real state | Real location |
|---|---|---|---|
| Fixed chunking of 256 tokens, overlap 30, `tiktoken` | §2 | Statistical semantic chunking, `max_tokens=400`, no overlap | `ingestion.py:48-108` |
| Purely vector retriever, cosine Top-K | §3, diagram | Hybrid vector + FTS search fused with RRF (`k=60`) | `retriever.py:34-58` |
| Reranker `ms-marco-TinyBERT-L-2-v2` | §3 | `ms-marco-MiniLM-L-12-v2` | `reranker.py:10` |
| Linear pipeline Ingestion → Retrieval → Generation | diagram | Cyclic 3-node `StateGraph` with a review loop | `graph.py:20-51` |
| Evals with DeepEval in `tests/test_rag.py` | §6 | Broken suite that cannot run | `BUG-07` |
| No mention of multi-tenancy, RLS, GraphRAG, memory, cache or evaluator | — | All five implemented | Phases 3-4 |

The Mermaid diagram at the top describes the whole Phase 1 linear pipeline, including the labels *"Phase 1: Ingestion"*, *"Phase 2: Retrieval"*, *"Phase 3: Generation"*, a naming that also **collides** with the README roadmap's Phases 1–4, which mean something else.

**Impact.** A reader who starts with `ARCHITECTURE.md` builds a wrong mental model of the system and reaches `PAPER.md` with contradictory expectations. For a portfolio repository, it is the document most likely to be opened first after the README.

**Reproduction.** Compare `ARCHITECTURE.md` §2 with `src/services/ingestion.py:48`, and §3 with `src/services/retriever.py:34`.

**Patch.** A banner at the top of the file, the minimum viable:

```markdown
> ⚠️ **Historical document (Phases 1–2).** It describes the original linear pipeline,
> replaced in Phase 4 by the multi-agent architecture. It is kept as a record of
> how the project evolved.
> For the current architecture, see **[docs/PAPER.md](docs/PAPER.md)**.
```

A better alternative: rewrite it as a technical summary of the current architecture (the gap that today only a 478-line paper covers) and move the historical content to `docs/ARCHITECTURE_PHASE_1.md`.

---

### `DOC-06` 🟡 Chunking: 400 tokens in the code vs. 500 in the paper

**What the documentation says.**

`PAPER.md` §5.2:
> *"…or if the accumulated tokens of the current chunk exceed the strict upper limit $L_{max} = 500$ tokens (Line 26)."*

`PAPER_PLAN.md` §3.9: *"or the chunk's accumulated tokens exceed `max_tokens=500`"*.

**What the code does.** `src/services/ingestion.py:48`:

```python
def chunk_text(content: str, source_type: str, max_tokens: int = 400, overlap: int = 0) -> List[DocumentChunk]:
```

and the real break condition (l. 91):

```python
if dist > threshold or (current_chunk_tokens + tokens_count) > max_tokens:
```

**Additional divergence: the `overlap` parameter is dead code.** It is declared with a default of `0` and **never read** in the function's body. It is a leftover of Phase 1's fixed-size implementation (which did use an overlap of 30, according to `ARCHITECTURE.md` §2). Its presence suggests that semantic chunking supports overlap; it does not.

**Additional divergence: the paper's line references are out of date.** The paper cites specific locations that no longer match:

| The paper cites | Real line |
|---|---|
| §5.1: *"lines 33-34"* for the RRF formula in `retriever.py` | 54 |
| §5.2: *"lines 18-20"* for `cosine_distance` | 39-45 |
| §5.2: *"Line 23"* for the threshold $\tau$ | 78 |
| §5.2: *"Line 26"* for the token limit | 91 |
| §5.4: *"Line 10"* for `route_reviewer` in `graph.py` | 11-18 |
| §5.6: *"Lines 42-44"* for the `CHECK`s in `01_init.sql` | 64-66 |

**What is correct.** The rest of the §5.2 formalization is exact: the cosine distance formula, the threshold $\tau = \mu + 1.25\sigma$ (`ingestion.py:78`), and the disjunctive break condition. Only the constant and the lines diverge.

**Reproduction.**

```bash
grep -n "max_tokens\|overlap" src/services/ingestion.py | head -5
grep -n "500\|L_{max}" docs/PAPER.md | head -3
```

**Patch.** Decide which value is right (`400` is in the code and is what runs) and align both papers. Remove the dead parameter:

```diff
-def chunk_text(content: str, source_type: str, max_tokens: int = 400, overlap: int = 0) -> List[DocumentChunk]:
+def chunk_text(content: str, source_type: str, max_tokens: int = 400) -> List[DocumentChunk]:
```

For the line references: cite by **function name** instead of by number. `(`chunk_text`, break condition)` does not age; `(Line 26)` ages with the next commit. It is the root cause of six of this finding's divergences.

---

### `DOC-07` 🟡 LLM model misquoted throughout the documentation

**What the documentation says.**

- `README.md`, badge: `![Anthropic](https://img.shields.io/badge/LLM-Claude%20Haiku-purple.svg)`
- `README.md` §Stack: *"`Anthropic Claude 3.5 Haiku` + `Instructor` + `Pydantic v2`"*
- `src/services/extractor.py:40`, comment: *"# Claude 3.5 Haiku o Sonnet son ideales para esto."* ("Claude 3.5 Haiku or Sonnet are ideal for this.")

**What the code does.** The seven calls use `claude-haiku-4-5-20251001`:

| File:line | Function | `max_tokens` |
|---|---|:---:|
| `router.py:75` | `analyze_query` | 500 |
| `extractor.py:42` | `generate_answer` | 8192 |
| `extractor.py:77` | `generate_answer_stream` (dead) | 8192 |
| `memory.py:37` | `extract_and_save_facts` | 200 |
| `graphrag.py:36` | `extract_knowledge_graph` | 1024 |
| `evaluator.py:59` | `evaluate_rag_response` | 300 |
| `ingestion.py:118` | `describe_image_with_claude` | 1000 |

**Analysis.** The comment in `router.py:72-73` documents the real decision:

```python
# Usamos claude-haiku-4-5-20251001 que descubrimos que funciona perfecto en tu cuenta
# Haiku es súper rápido y barato, ideal para ruteo
```

("We use claude-haiku-4-5-20251001, which we found works perfectly on this account. Haiku is very fast and cheap, ideal for routing.") The choice is right and well justified. What fails is the public documentation, which cites a model from an earlier generation.

**A related maintenance problem.** The identifier is **repeated literally seven times**. Any model migration requires seven coordinated edits, with the risk of leaving modules out of step. It is exactly the kind of coupling the rest of the project avoids (the thresholds, on the other hand, are centralized as function defaults).

**Reproduction.**

```bash
grep -rn "claude-haiku" src/ | wc -l          # 7
grep -rn "3.5 Haiku\|Claude 3.5" README.md src/  # README §Stack + extractor.py:40
```

**Patch.** Centralize and correct. Create `src/services/llm_config.py`:

```python
import os

# Default model for every task in the system.
# Haiku: low latency and low cost, enough for routing, extraction and evaluation.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
```

The seven call sites move to `model=ANTHROPIC_MODEL`. Update the README badge and stack section, and the comment in `extractor.py:40`.

With the environment variable, moreover, a more capable model can be tried in the generator without touching code, which is useful for the trade-off `PAPER.md` §9 discusses.

---

### `DOC-08` ⚪ Python 3.12 (badge) vs. 3.14 (`requires-python`)

**What the `README.md` says.** Badge: `![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)`. Stack section: *"Backend framework: `FastAPI` (Python 3.12+, fully asynchronous)"*.

**What the build requires.** `pyproject.toml:3`:

```toml
requires-python = ">=3.14"
```

The verified environment runs Python 3.14.0.

**Impact.** A user with Python 3.12 (who meets exactly what the README asks for) fails at `uv sync` with a version resolution error. It is the first step of the installation instructions.

**Reproduction.**

```bash
grep -n "requires-python" pyproject.toml    # 3: >=3.14
grep -n "3.12" README.md                     # badge + stack section
```

**Patch.** Align the badge and the section to `3.14+`, or relax `requires-python` to `>=3.12` if there is no real dependency on 3.13/3.14 features (none was found in the code: there is no syntax exclusive to those versions). The second option widens the base of users who can run the project; the first is more honest about the tested environment.

---

## 8. Repository Hygiene

### `HYG-01` 🟡 Undeclared direct dependencies

**Analysis.** Three packages are imported in the code but **are not listed in `pyproject.toml`**:

| Package | Imported in | Use | Comes in through |
|---|---|---|---|
| `pyjwt` | `src/api/auth.py:6` (`import jwt`) | Signing and verifying tokens | transitive |
| `numpy` | `src/services/ingestion.py:37` | `mean`, `std`, `dot`, `linalg.norm` in the chunking | transitive from `sentence-transformers` |
| `python-multipart` | required by `UploadFile` in `src/api/routers/ingest.py:14` | Parsing multipart forms | transitive from `fastapi` |

Verified in the environment: `pyjwt` 2.13.0, `numpy` 2.5.2, `python-multipart` 0.0.32, installed, but not through a declaration of the project's own.

**Impact.** They work only as long as some other dependency keeps pulling them in. If `sentence-transformers` moved to a backend without an explicit `numpy`, or if `fastapi` moved `python-multipart` to an optional extra, the failure would happen at runtime (`ImportError` at startup for `pyjwt`; `RuntimeError: Form data requires "python-multipart"` on the first upload) without any change in the project's own code.

**The reverse problem: an unnecessary heavy dependency.** `deepeval==4.2.1` is declared as a **production** dependency, but its only consumer (`tests/test_rag.py`) is broken (`BUG-07`). It pulls a sizeable tree into the final image. The same applies to `pytest>=9.1.1`.

`pytest-asyncio` is also missing, without which the `@pytest.mark.asyncio` in `tests/test_rag.py:18` has no effect: the async tests would be silently skipped even if `BUG-07` were fixed.

**A minor contradiction.** `CONTEXT.md` §Coding rules states: *"Zero unnecessary heavy dependencies (use `flashrank` instead of `torch`)"*. The rule is good and `flashrank` follows it, but `sentence-transformers` pulls in `torch` anyway, and `deepeval` adds another unused tree.

**Reproduction.**

```bash
grep -iE "jwt|numpy|multipart|pytest-asyncio" pyproject.toml   # no matches
grep -rn "^import jwt\|^import numpy\|import numpy as np" src/
```

**Patch.**

```diff
 dependencies = [
     "anthropic==1.4.0",
     "asyncpg>=0.31.0",
-    "deepeval==4.2.1",
     "fastapi>=0.141.1",
     "flashrank>=0.2.10",
     "instructor>=1.16.0",
     "langchain-core>=1.6.2",
     "langfuse>=4.15.1",
     "langgraph>=1.2.11",
+    "numpy>=2.0",
     "pillow>=12.3.0",
     "pydantic>=2.13.5",
+    "pyjwt>=2.10",
     "pymupdf>=1.28.2",
-    "pytest>=9.1.1",
     "python-dotenv>=1.2.3",
+    "python-multipart>=0.0.20",
     "requests>=2.34.2",
     "sentence-transformers>=6.0.1",
     "streamlit==1.63.0",
     "tiktoken>=0.14.0",
     "uvicorn>=0.52.4",
 ]
+
+[dependency-groups]
+dev = [
+    "deepeval==4.2.1",
+    "pytest>=9.1.1",
+    "pytest-asyncio>=0.24",
+]
```

**No longer just a risk (checked on 2026-09-16).** `pyjwt` is neither in `pyproject.toml` nor in `uv.lock`, and `uv sync`, which the README tells you to run, leaves the environment exactly as the lockfile says. `uv sync --dry-run` on the project's `.venv`: *"Would uninstall 10 packages"*, among them `pyjwt==2.13.0`, which `src/api/auth.py:9` imports. So following the README from a clean clone produces an API that does not start. `uv run` does not suffer from it, because it syncs without uninstalling what is left over. That is why `BUG-07` moved `pytest` to the `dev` group with `uv add --dev --no-sync` and the suite runs with `uv run pytest`. `pytest-asyncio` is already declared.

**Status:** 🟡 partly fixed on 2026-11-09, before publishing the repository. `pyjwt>=2.13.0`, `numpy>=2.5.2` and `python-multipart>=0.0.32` are now declared (with `uv add --no-sync`). Verified from a clean clone, following the README with `uv sync`: before, `import jwt` fails and `tests/api` cannot even be collected (`ModuleNotFoundError: No module named 'jwt'`); after, `pyjwt` 2.15.1 is installed, survives a second `uv sync` and `uv run pytest -m "not db"` gives `111 passed`. Moving `deepeval` to the `dev` group remains open. This verification turned up `HYG-10`.

**A note on the uncommitted pins.** The pending diff in the working tree pins three exact versions (`anthropic==1.4.0`, `deepeval==4.2.1`, `streamlit==1.63.0`) where there used to be ranges. Pinning is defensible for reproducibility, but it should be a conscious, documented decision, not a debugging leftover, and `uv.lock` already guarantees exact reproducibility on its own.

---

### `HYG-02` 🟡 Dead code committed in the root

**Analysis.** Nine files that `PAPER_PLAN.md` §5.2 already identifies as *"the developer's iterative local validation scripts (dead code/experiments)"* are still committed:

| File | Location | State |
|---|---|---|
| `test_chunk.py` | root | local validation script |
| `test_db.py` | root | local validation script |
| `test_sim.py` | root | local validation script |
| `test_sse.py` | root | local validation script |
| `scratch_db.py` | root | experiment |
| `scratch_stream.py` | root | experiment |
| `src/pipeline.py` | `src/` | Phase 1 pipeline, broken (`TypeError`, same as `BUG-07`) |
| `src/models/requests.py:10-11` | — | `IngestRequest` never used |
| `uvicorn.log` | root | run log (see `HYG-03`) |

**Specific impact of the root `test_*.py` files.** `pytest` discovers them by naming convention. A `uv run pytest` from the root tries to collect them together with `tests/test_rag.py`, mixing exploration scripts with the real suite. Since several run code at module level (database connections, model loading), collection itself has side effects.

**Impact on how the repository reads.** For a portfolio repository, nine dead files in the root are the first thing anyone running `ls` sees. They compete visually with the five files that do matter.

**Reproduction.**

```bash
ls *.py
# scratch_db.py  scratch_stream.py  test_chunk.py  test_db.py  test_sim.py  test_sse.py
```

**Patch.** Delete them (git history keeps them whole, and they can be recovered with `git log --all --diff-filter=D`):

```bash
git rm test_chunk.py test_db.py test_sim.py test_sse.py scratch_db.py scratch_stream.py
git rm src/pipeline.py          # or fix it if it is to be kept as a Phase 1 demo
git rm --cached uvicorn.log
```

If keeping them is preferred, move them to `scratch/` (out of pytest's discovery path) with a one-line `README` explaining what they are.

Also remove `IngestRequest` from `src/models/requests.py`.

---

### `HYG-03` ⚪ Incomplete `.gitignore`

**Current content:**

```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.DS_Store
```

**What is missing.** Two items are committed and should not be:

1. **`.idea/`**: 9 PyCharm configuration files, including `workspace.xml`, which holds local editor state (open files, cursor position, run history). It changes every session and creates constant noise in `git status`.
2. **`uvicorn.log`** (153 B): a run log.

Preventive entries are missing too: `/tmp/flashrank` is outside the repo (`reranker.py:10` uses `cache_dir="/tmp/flashrank"`), and so is the `sentence-transformers` cache (`~/.cache/huggingface`), so there is no immediate risk. It would be worth covering build artifacts (`dist/`, `*.egg-info/`) and coverage ones (`.coverage`, `htmlcov/`) if CI is added.

**Reproduction.**

```bash
git ls-files | grep -E "\.idea|\.log"
```

**Patch.**

```diff
 .env
 .venv/
 __pycache__/
 *.pyc
 .pytest_cache/
 .DS_Store
+
+# IDE
+.idea/
+.vscode/
+
+# Logs and artifacts
+*.log
+dist/
+*.egg-info/
+.coverage
+htmlcov/
```

And take them out of the index: `git rm -r --cached .idea uvicorn.log`.

---

### `HYG-04` ⚪ Deprecated `datetime.utcnow()`

**Location.** `src/api/auth.py:38-46`

```python
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta        # ← l. 41
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)  # ← l. 43
```

**Analysis.** `datetime.utcnow()` has been deprecated since Python 3.12. The project requires 3.14 (`DOC-08`), where it emits a `DeprecationWarning` on every token issued.

The underlying problem is that it returns a **naive** `datetime` (no `tzinfo`), which has historically caused comparison errors between local and UTC times. There is no functional bug here (PyJWT converts to a Unix timestamp assuming UTC, which is right) but the pattern is fragile.

**Reproduction.**

```bash
grep -n "utcnow" src/api/auth.py    # 41, 43
```

**Patch.**

```diff
-from datetime import datetime, timedelta
+from datetime import datetime, timedelta, timezone
@@
-        expire = datetime.utcnow() + expires_delta
+        expire = datetime.now(timezone.utc) + expires_delta
     else:
-        expire = datetime.utcnow() + timedelta(minutes=15)
+        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
```

---

### `HYG-05` 🟡 Three services create their Anthropic client before loading `.env`

> After the snapshot: found on 2026-09-14 while verifying `BUG-02`. The note in §3.3 pointed it out only for `evaluator.py` and without cataloguing it.

**Location.** At import time, without having called `load_dotenv()`:

| File:line | What it reads from the environment |
|---|---|
| `src/services/router.py:10` | `ANTHROPIC_API_KEY` |
| `src/services/extractor.py:13` | `ANTHROPIC_API_KEY` |
| `src/services/evaluator.py:12` | `ANTHROPIC_API_KEY` and, at l. 11, `DATABASE_URL` |

**Analysis.** They work only because `src/api/main.py` first imports modules that do load `.env` (`auth.py`, `cache.py`, `memory.py`…). Any entry point that imports the graph or these services first creates the clients without a key: a script, a test, a worker. And the failure does not show up on import, but on the first LLM call. `evaluator.py` would also fall back to the default DSN.

**Evidence.** Verifying `BUG-02`, a launcher that imported `src.services.agent_graph.nodes` before `src.api.main` made all 11 requests fail with *"Could not resolve authentication method. Expected either api_key or auth_token to be set"*. Loading `.env` before any import solved it.

**Reproduction.**

```bash
for f in src/services/*.py; do
  grep -q "AsyncAnthropic(" "$f" && ! grep -q "load_dotenv()" "$f" && echo "$f"
done
# src/services/evaluator.py, src/services/extractor.py, src/services/router.py
```

**Patch.** A single `src/config.py` that calls `load_dotenv()` and exposes the variables, imported by every service before reading the environment. Another option is to create the clients lazily on the first call. It fits with the single `ANTHROPIC_MODEL` that `DOC-07` proposes.

---

### `HYG-06` ⚪ The database does not restart with Docker

> After the snapshot: found on 2026-09-14 during the verification of `BUG-05`.

**Location.** `docker-compose.yml`: the `postgres` service does not declare `restart`.

**Analysis.** After restarting Docker Desktop or the machine, the container stays stopped and the API fails with connection refused on port 5433, with nothing indicating why.

**Evidence.** On 2026-09-14 at 17:37:52 UTC, Docker Desktop restarted in the middle of a verification. The three running containers stopped at the same instant. The two that had a restart policy came back on their own; the sandbox's did not. The shutdown was clean and no data was lost.

**Patch.**

```yaml
  postgres:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
```

**Status:** ✅ fixed on 2026-09-16.

**Verification.** From a clean clone, in disposable Compose projects with their own port, a server crash was caused with `pg_ctl stop -m immediate` inside the container. With the old compose file, the container stays `exited` and nothing brings it up. With the new one, Docker restarts it on its own (`restarts=1`, `running`). Afterwards, a manual `docker stop` leaves it stopped, which is what sets `unless-stopped` apart from `always`. The Docker Desktop restart, which is the original evidence, was not reproduced so as not to take down the machine's other containers. That case is covered by the policy's definition: a container that was not stopped by hand comes back when the daemon starts.

**Development database.** `docker compose up -d` recreated the container with the new policy on the same `ai_engineer_sandbox_pgdata` volume: 22 / 128 / 4 / 3 / 0 before and after.

---

### `HYG-07` 🟡 `ALTER DEFAULT PRIVILEGES` hands `app_user` every future table in `public`

> After the snapshot: found on 2026-09-15 while implementing `SEC-05`.

**Location.** `sql/00_create_app_user.sql:5`.

```sql
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO app_user;
```

**Analysis.** It does not grant privileges on today's tables, but on every table the superuser creates tomorrow in `public`. Any new table is born with an explicit `GRANT ALL` to `app_user`, including those created precisely so that the application role cannot read them. And since the privilege is a `GRANT` to the role, not to `PUBLIC`, a `REVOKE ALL ... FROM PUBLIC` does not remove it: it has to be revoked from the role by name, or the table created outside `public`.

The two previous lines of the same script (`GRANT ... ON ALL TABLES` and `ON ALL SEQUENCES`) run before any table exists, so they do nothing; the application's real privileges are granted by `sql/01_init.sql` at the end, table by table. This line is therefore unnecessary.

**Evidence.** The first version of the `SEC-05` patch stored the signing key in `public.tenant_signing_key` with `REVOKE ALL ON TABLE ... FROM PUBLIC`. Against a database freshly created from an empty volume, `has_table_privilege('app_user', 'tenant_signing_key', 'SELECT')` returned `true`, and as `app_user`:

```
SELECT key FROM tenant_signing_key;   -- b9f23fd87455c8eda71ebebafeaa4f94...
```

With that key in sight, `app_user` could sign any tenant and `SEC-05` had no effect, despite passing the rest of the isolation tests.

**Reproduction.**

```sql
-- as postgres
CREATE TABLE secret (data TEXT);
REVOKE ALL ON TABLE secret FROM PUBLIC;
SELECT has_table_privilege('app_user', 'secret', 'SELECT');   -- true
```

**Patch.** Delete the line (the application's five tables already get their explicit `GRANT` in `01_init.sql`). While it stays there, any object that must stay out of `app_user`'s reach goes in a separate schema, as the `SEC-05` key already does in `tenant_security`.

**Status:** ✅ fixed on 2026-09-16.

**Changes.** `sql/00_create_app_user.sql` loses the `ALTER DEFAULT PRIVILEGES` and the two `GRANT ... ON ALL TABLES/SEQUENCES`, which did nothing because they run before any table exists. There are no sequences either: the keys are `UUID`. `app_user`'s privileges on tables are now only the explicit `GRANT`s at the end of `01_init.sql`. Since the bootstrap script does not touch a database that already exists, `sql/migrations/apply_revoke_default_privileges.sql` revokes the default privilege (`ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM app_user`). The application creates no tables at runtime, so nothing depended on that privilege.

**Verification.** The entry's reproduction was done as `postgres` inside a transaction that is rolled back, so the table never came to exist:

| | Development database | New database from a clean clone |
|---|---|---|
| Before: rows in `pg_default_acl` | 1 | 1 |
| Before: `app_user` reads the new table | `true` | `true` |
| After: rows in `pg_default_acl` | 0 | 0 |
| After: `app_user` reads the new table | `false` | `false` |

A check that nothing breaks: the five tables keep `SELECT, INSERT, UPDATE, DELETE` for `app_user` in both variants. With a signed context, `app_user` inserts, updates, reads (1/1/1/1/1) and deletes on all five, inside a rolled-back transaction. `tenant_security.signing_key` is still unreadable. The `pg_dump --schema-only` of the two new databases differs only in the `DEFAULT ACL` block. Development database, 22 / 128 / 4 / 3 / 0 before and after.

The `tenant_security` schema from `SEC-05` stays: it is no longer needed to dodge this privilege, but it does not depend on nobody adding it back.

---

### `HYG-08` 🟠 The database data lives in an anonymous volume

> After the snapshot: found on 2026-09-16, while reviewing the state of Docker.

**Location.** `docker-compose.yml`: the `postgres` service mounts `./sql` on `/docker-entrypoint-initdb.d`, but declares nothing for `/var/lib/postgresql/data`.

**Analysis.** The `pgvector/pgvector:pg16` image declares `VOLUME /var/lib/postgresql/data`, so Docker creates an **anonymous** volume on the first start. The data persists (it survives `stop`/`start`), but in a volume whose name is a hash, indistinguishable from any other anonymous volume on the machine and not referenced from the project.

The risk is not losing data through a failure, but through a routine command:

| Action | Effect |
|---|---|
| `docker stop` / `start` | The data survives |
| `docker compose down` | The container disappears and the volume is **orphaned**; a later `up` creates a new, empty one, and the database shows up empty without anything failing |
| `docker compose down -v` | The data is deleted, with no recovery |
| `docker volume prune` | Takes the orphaned anonymous volumes with it |

It is the same pattern as `BUG-08` (the re-ranker cache in `/tmp`): state that matters, stored where nobody declares it.

**Evidence.** On the development container, after 41 hours running:

```
$ docker inspect ai_engineer_sandbox-postgres-1 -f '{{range .Mounts}}...{{end}}'
bind   | source=<repo>/sql | destination=/docker-entrypoint-initdb.d
volume | source=5b179a9ea01f43aa9f977868ee27c1216570a8f846c5932cc53428eec304a9cd
       | destination=/var/lib/postgresql/data

$ docker inspect pgvector/pgvector:pg16 -f '{{json .Config.Volumes}}'
{"/var/lib/postgresql/data":{}}
```

`docker volume ls` shows no volume named after the project; there are 3 anonymous ones on the machine. The behavior with `-v` is checked here: doing `down -v` on the disposable project used in `SEC-05` and starting it again, the database came up empty. The case without `-v` is documented Compose behavior, not verified on this machine.

**Patch.** Declare a named volume:

```yaml
services:
  postgres:
    volumes:
      - ./sql:/docker-entrypoint-initdb.d
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

**Watch out when applying it:** the change migrates nothing. When starting with the named volume, Postgres starts on an empty volume, runs the init scripts, and the current development database (22 documents, 128 triples, 4 cache rows, 3 memory rows) stays behind in the anonymous volume, orphaned. To keep it, it has to be dumped first (`pg_dump`) and restored afterwards, or the volume's contents copied. It is an operation on the only copy of that data, so the user decides.

**Status:** ✅ fixed on 2026-09-16, at the user's request and with a verified backup first.

**Backup.** Before touching anything: a `pg_dump` of the database and `pg_dumpall --roles-only`, outside the repository and with `600` permissions, because the dump includes the `SEC-05` HMAC key. It was verified by restoring it into a disposable Postgres: 22 / 128 / 4 / 3 / 0, the key intact and isolation standing (128 rows with a signature, 0 without).

**Migration.** With the named volume declared, `compose up` created it with its labels and recreated the container; Postgres was stopped, **checking explicitly** that it was no longer running, and the anonymous volume (mounted read-only) was copied onto the named one. Result: 1019 files on both sides, the same `PG_VERSION`, owner `999:999` and `diff -r` with no differences. On startup, Postgres logged `database system was shut down at …` without any recovery line, which confirms the copy comes from a clean shutdown. Counts, key and isolation identical to the backup's. The original anonymous volume is kept, orphaned on purpose, until the user decides to delete it.

**Negative control**, in two disposable projects and with the same sequence (write a marker row, `docker compose down` **without** `-v`, `up` and read it):

| | Previous compose (`HEAD`) | Fixed compose |
|---|---|---|
| Data volume before / after | `6b0d2ffb…` / `cb47e5f8…` (different) | `hyg08despues_pgdata` / the same |
| Marker row after `down` + `up` | `relation "marca_hyg08" does not exist` | `sobrevivo` ("I survive") |
| Previous volume | left orphaned | — |

This also verifies the case without `-v`, which the evidence above gave only as documented Compose behavior. It is still true that `down -v` and `docker volume prune` delete the data: a named volume protects against carelessness, not against the explicit order to delete.

**An incident during the migration.** The first attempt left out the root-level `volumes:` declaration. Compose rejected the project, but the failure was hidden because each command ran in a pipe (`| tail`) and `set -e` only looks at the exit code of the pipe's last command: the `stop` never ran and the copy was made with Postgres running, onto a volume `docker run` created without Compose's labels. There was no damage (the source was read-only and the development container kept running with 22 / 128 / 4 / 3 / 0 and no errors in the log), but the hot copy was thrown away and the process was repeated with `set -o pipefail` and explicit checks before each destructive step.

**Update (2026-11-09).** The Docker Desktop virtual machine was recreated on 2026-11-07 (that is the date of its data directory), and with it every volume on the machine was lost, including `ai_engineer_sandbox_pgdata` and the orphaned anonymous volume. It was not a `down -v` or a `prune`, so no volume configuration could have prevented it. The September 16 backup (`~/Backups/ai_engineer_sandbox/`) survives: it was restored into a disposable container for the English-translation verification, with the same 22 / 128 / 4 / 3 / 0 counts and the signing key matching `.env`.

---

### `HYG-09` ⚪ `onnxruntime` telemetry aborts the process on shutdown

> After the snapshot: found on 2026-09-17, while closing the API regression layer.

**Location.** `src/services/reranker.py:38` creates FlashRank's `Ranker`, which loads `onnxruntime`. The package ships Microsoft's compiled telemetry client (*1DS / Microsoft::Applications::Events*), which starts a thread of its own.

**Analysis.** That thread makes HTTP requests and processes their responses. If one arrives when the interpreter is already shutting down, it takes an already destroyed `recursive_mutex`, the exception escapes and the process ends with `abort` (code 134). It happens **after** the program has done its work, so it corrupts nothing, but a process that finished well returns an error code: any automation that looks at the exit code considers it failed.

**Evidence.** The full suite (129 tests) ended that way in **7 of every 8 runs**, always after printing `129 passed`:

```
129 passed in 18.39s
libc++abi: terminating due to uncaught exception of type std::__1::system_error:
    recursive_mutex lock failed: Invalid argument
```

The macOS report (`~/Library/Logs/DiagnosticReports/python3.14-*.ips`) points to the culprit thread:

```
onnxruntime_pybind11_state.so | Microsoft::Applications::Events::HttpClientManager::onHttpResponse
onnxruntime_pybind11_state.so | Microsoft::Applications::Events::LogManagerImpl::DispatchEvent
libc++.1.dylib                | std::__1::recursive_mutex::lock()  ->  __cxa_throw  ->  abort
```

It only appeared in the full suite, the only one that loads FlashRank (when importing the application) and lasts long enough for the telemetry to complete a round trip. The layers on their own do not reproduce it (3 of 3 clean each), and neither does importing the application and exiting (0 of 8), which is too short.

**Reach into the real application: not reproduced.** Three uvicorn starts with a request to `/health` and a stop with `SIGTERM` after 25 s ended in 143 (the `SIGTERM` itself), without `abort`. It cannot be ruled out in a long-lived process that ends on its own.

**Patch applied (tests only).** `tests/conftest.py` calls `onnxruntime.disable_telemetry_events()` before anything imports the re-ranker. Measured: from 7 failures in 8 runs to **0 in 20**. Disabling it later is not enough: doing it when importing the application, 2 of 8 still failed, because the thread was already running.

**Status:** ✅ fixed on 2026-09-17, at the user's request, in both places.

`src/services/reranker.py` disables the telemetry **before importing FlashRank**. Where matters: the first version of the patch disabled it right before creating the `Ranker`, with `onnxruntime` already imported by the `from flashrank import ...` line, and it was not enough.

| Configuration | Full suite runs that abort |
|---|:---:|
| Nothing | 7 of 8 |
| `reranker.py` only, after importing FlashRank | 3 of 8 |
| `reranker.py` only, before importing FlashRank | 1 of 8 |
| `tests/conftest.py` only | 0 of 20 |
| Both | 0 of 10 |

Disabling it earlier shrinks the window, it does not close it: the earlier it is done, the more time the in-flight request has to finish during the run and not at shutdown. That is why both stay, and the production one also protects the API, ingestion and any script that loads the re-ranker.

**A check that nothing changes.** The same re-ranking before and after the patch, with four documents and a fixed question: `d1` 0.99872, `d4` 0.370157, `d3` 0.000014, in that order.

---

### `HYG-10` 🟠 `uv sync` picks Python 3.15 and the install fails

> After the snapshot: found on 2026-11-09, while verifying `HYG-01` from a clean clone before publishing the repository.

**Location.** `pyproject.toml:4` (`requires-python = ">=3.14"`), without a `.python-version` in the repository.

**Analysis.** Without a `.python-version`, `uv` takes the newest interpreter that meets `>=3.14`. On a machine that has 3.15, that is 3.15, and `onnxruntime` (it comes with FlashRank) publishes no wheels for it. Step 1 of the README fails for anyone with 3.15 installed, even though the README asks for 3.14.

**Evidence.** `uv sync` on a clean clone:

```
error: Distribution `onnxruntime==1.29.0 @ registry+https://pypi.org/simple` can't be installed
because it doesn't have a source distribution or wheel for the current platform

hint: You're using CPython 3.15 (`cp315`), but `onnxruntime` (v1.29.0) only has wheels with
the following Python ABI tags: `cp314`, `cp314t`
```

**Status:** ✅ fixed on 2026-11-09. `.python-version` with `3.14`. On the same clone, `uv sync` uses CPython 3.14.8 and finishes without error; with `HYG-01` fixed, the suite without Docker gives `111 passed`. `requires-python` is left as it is: the problem is which interpreter is picked, not which ones are allowed.

---

## 9. Annotated End-to-End Trace

The path of a real query through the system, pointing out where each finding kicks in. Scenario: a user authenticated as `bryan` sends *"¿Y en qué años trabajó con eso?"* ("And in which years did he work with that?") as the **second** question of the conversation, after asking about AWS.

| # | Step | Location | Active findings |
|:---:|---|---|---|
| 1 | Streamlit builds the payload with `query` + `history` (1 previous turn) | `frontend/app.py:87-88` | — |
| 2 | `POST /chat/stream/` with `Authorization: Bearer <jwt>` | `frontend/app.py:91` | — |
| 3 | `get_current_user` decodes the token, extracts `tenant_id` as an unvalidated `str` | `auth.py:72-80` | 🔴 `SEC-01` 🔴 `SEC-02` |
| 4 | `check_semantic_cache`: opens connection #1, `SET app.current_tenant` with an f-string, looks for similarity ≥ 0.85 | `chat.py:77` → `cache.py:21-41` | 🟠 `PERF-01` 🔴 `SEC-02` |
| 5 | *If there was a hit:* returns the answer with the progress prefix embedded + `⚡ [CACHE HIT]` and ends | `chat.py:79-81` | 🟠 `BUG-01` 🟠 `BUG-02` |
| 6 | `retrieve_user_facts`: connection #2, top-3 facts with similarity > 0.3, wrapped in `<USER_PROFILE>` | `chat.py:83` → `memory.py:70-95` | 🟠 `PERF-01` |
| 7 | `initial_state` is built. **`request.history` is not copied** | `chat.py:85-96` | 🟠 `BUG-03` |
| 8 | `supervisor_node` → `analyze_query(query, [])` with an empty history | `nodes.py:18` | 🟠 `BUG-03` |
| 9 | Claude classifies the intent **without previous context**: "¿Y en qué años trabajó con eso?" makes no sense on its own → probably `out_of_scope` or `knowledge_search` with generic variants | `router.py:74-79` | 🟠 `BUG-03` 🟡 `DOC-07` |
| 10 | *If `tool_execution`:* a synchronous `requests.get()` blocks the event loop for up to 5 s | `nodes.py:40` → `tools.py` | 🟡 `PERF-03` |
| 11 | `researcher_node`: 5 × `retrieve_documents` in `asyncio.gather` → **5 simultaneous connections**, hardcoded `top_k=15` | `nodes.py:70-71` | 🟠 `PERF-01` 🟡 `BUG-06` 🔴 `SEC-02` |
| 12 | Deduplication by exact `content` over ~75 candidates | `nodes.py:74-80` | ✅ correct |
| 13 | `rerank_documents` with FlashRank, hardcoded `top_k=10` (the contract says 7) | `nodes.py:83` | 🟡 `BUG-06` |
| 14 | `retrieve_subgraph`: connection #7, concatenated `WHERE`, full *seq scan* | `nodes.py:86` → `graphrag.py:78-89` | 🟠 `SEC-03` 🟠 `PERF-01` |
| 15 | Subgraph injected at index 0, skipping the reranker | `nodes.py:87-93` | ✅ correct and well documented |
| 16 | `generator_node` → `generate_answer` (**not** `generate_answer_stream`) | `nodes.py:107` | 🟠 `DOC-01` |
| 17 | Claude generates the full answer; `max_tokens=8192` | `extractor.py:41-48` | 🟡 `DOC-07` |
| 18 | `route_reviewer`: if `requires_more_info` → back to `researcher` **with the same queries** | `graph.py:11-18` | 🟡 `BUG-05` |
| 19 | *If it iterated:* +6 connections, +1 LLM call, identical result | `nodes.py:61-95` | 🟡 `BUG-05` 🟠 `PERF-01` |
| 20 | SSE emits 4 discrete events, not tokens | `chat.py:102-120` | 🟠 `DOC-01` |
| 21 | `final_dict["answer"] = accumulated_answer + answer` | `chat.py:119` | 🟠 `BUG-01` |
| 22 | `save_semantic_cache` stores the **polluted** dict, connection #8 | `chat.py:123` | 🟠 `BUG-01` 🟠 `PERF-01` |
| 23 | `extract_and_save_facts` in the background: LLM + connection #9 | `chat.py:124` → `memory.py:36-62` | 🟠 `PERF-01` |
| 24 | `evaluate_rag_response` in the background: gets the polluted answer, `max_tokens=300`, no `ge`/`le`, connection #10 | `chat.py:127` → `evaluator.py` | 🟠 `BUG-01` 🟡 `PERF-04` 🟠 `DOC-02` 🟠 `PERF-01` |
| 25 | If the evaluator truncated or returned an out-of-range score: exception swallowed, evaluation lost without a trace | `evaluator.py:86` | 🟡 `PERF-04` 🟠 `DOC-02` |

**Connection count for this trace:** 10 without a retry, 16 with a retry.

**Observation.** Step 9 is where `BUG-03` does its real damage: a perfectly natural follow-up question cannot be resolved because the supervisor does not see the previous turn. Every later step works correctly on a wrong interpretation of the question.

---

## 10. Remediation Plan

Ordered by impact/effort ratio. The estimates are for implementation, not including testing.

### Progress as of 2026-09-14

| Block | Status |
|---|---|
| 0 — Unblocking | ✅ closed (`BUG-08`) |
| 1 — Security | ✅ closed (`SEC-01` to `SEC-04`) |
| 2 — Functional correctness | ✅ closed (`BUG-01` to `BUG-06`, plus `BUG-09`) |
| 3 — Performance | ✅ closed (`PERF-01` to `PERF-04`, 2026-09-15) |
| 4 — Documentation reconciliation | ⬜ open (`DOC-01` and `DOC-02` already fixed) |
| 5 — Hygiene and coverage | ⬜ open |

The findings after the snapshot, with the block they fit in:

| # | Action | Finding | Block | Effort |
|:---:|---|---|:---:|:---:|
| 29 | ✅ done (2026-09-15). Tenant context signed with HMAC, verified by a `SECURITY DEFINER` function | `SEC-05` | 3, with step 12 | 2–4 h |
| 34 | ✅ done (2026-09-16). Remove the `ALTER DEFAULT PRIVILEGES` on `public` and revoke it in the existing database (it cannot be limited to specific tables) | `HYG-07` | 5 | 15 min |
| 35 | ✅ done (2026-09-16). Named volume for the data, with a verified backup and a cold migration of the current database | `HYG-08` | 5 | 30 min |
| 30 | ✅ done (2026-09-15). A generic message with an identifier for the client; the detail, only in the log | `SEC-06` | 1 | 20 min |
| 31 | ✅ done (2026-09-16). Do not use the cache when the request carries history | `BUG-10` | 2 | 15 min |
| 32 | `src/config.py` with `load_dotenv()` before creating clients | `HYG-05` | 5 | 20 min |
| 33 | ✅ done (2026-09-16). `restart: unless-stopped` on the `postgres` service | `HYG-06` | 5 | 2 min |
| 36 | 🟡 layer 1 done (2026-09-16): `GRANT CONNECT` instead of `GRANT ALL` on the database, and a migration for the existing one. Still to decide whether `search_path` is neutralized in the application and `pg_db_role_setting` watched (together with `BUG-07`) | `SEC-07` | 1 | 20 min (layer 1) |
| 37 | ✅ done (2026-09-17). `disable_telemetry_events()` before importing FlashRank, in `reranker.py` and in the tests | `HYG-09` | 5 | 5 min |
| 38 | ✅ done (2026-11-09). `.python-version` with `3.14` | `HYG-10` | 5 | 2 min |
| 39 | ✅ done (2026-11-10). One `threading.Lock` around every `model.encode` of the process | `BUG-12` | 2 | 15 min |
| D-01, D-02 | Data cleanups pending a decision (table in §1) | `SEC-04`, `BUG-02` | — | 5 min |

The checks for the fixes of blocks 0 to 2 ran from scripts outside the repository: negative controls against the real server and direct cases for routing, retrieval window, cache policy and validation. What is reproducible about them is in each finding's status line and in its commit message. Turning the cases that need neither a database nor an LLM into versioned tests is part of step 28 (`BUG-07`). Done on 2026-09-16: since then, most of them live in `tests/unit/` and `tests/db/`.

### Block 0 — Unblocking (a prerequisite for everything else)

| # | Action | Finding | Files | Effort |
|:---:|---|---|---|:---:|
| 0 | Move the FlashRank cache out of `/tmp` and clean up directories without a model | `BUG-08` | `reranker.py` | 10 min |

Without this the API does not start as soon as `/tmp` is emptied, and no other block can be verified.

### Block 1 — Security (blocking before any deployment)

| # | Action | Finding | Files | Effort |
|:---:|---|---|---|:---:|
| 1 | `SECRET_KEY` to an environment variable, with no default | `SEC-01` | `auth.py`, `.env.example` | 5 min |
| 2 | Type `User.tenant_id` as `uuid.UUID` | `SEC-02` | `auth.py` | 5 min |
| 3 | `NamedTemporaryFile` in ingestion | `SEC-04` | `ingest.py` | 10 min |
| 4 | Parameterized `ILIKE ANY($1::text[])` in GraphRAG | `SEC-03` | `graphrag.py` | 10 min |

The four close the two critical vulnerabilities and the two high ones in **half an hour**. It is the block with the highest return in the document.

### Block 2 — Functional correctness

| # | Action | Finding | Files | Effort |
|:---:|---|---|---|:---:|
| 5 | Separate the stream object from the object that is cached | `BUG-01` | `chat.py` | 15 min |
| 6 | `DELETE` the cache rows already polluted | `BUG-01` | one-off SQL | 5 min |
| 7 | Do not cache `tool_execution`, `out_of_scope` or low confidence | `BUG-02` | `chat.py` | 20 min |
| 8 | Pass `history` through to `analyze_query` | `BUG-03` | `state.py`, `chat.py`, `nodes.py` | 30 min |
| 9 | Reorder the SQL scripts; add `knowledge_graph` and `FORCE` to `01_init.sql` | `BUG-04` | `sql/`, `docker-compose.yml` | 30 min |
| 10 | Pass `top_k_retrieve` / `top_k_rerank` through | `BUG-06` | `state.py`, `chat.py`, `nodes.py` | 15 min |
| 11 | Decide about the loop: widen the search on retries, or disable it | `BUG-05` | `nodes.py`, `graph.py` | 1 h |

Step 6 is a **prerequisite** of step 5: without it, the poisoned rows are still served even though the code no longer produces them.

### Block 3 — Performance

| # | Action | Finding | Files | Effort |
|:---:|---|---|---|:---:|
| 12 | Connection pool in the `lifespan` + transaction-local `set_config` | `PERF-01`, `SEC-02` | `main.py` + 6 services | 2 h |
| 13 | `embeddings.py` module with a single instance and `to_pgvector` | `PERF-02` | new + 4 services | 30 min |
| 14 | `asyncio.to_thread` around `chunk_text` and around the tools | `PERF-03` | `ingestion.py`, `nodes.py` | 15 min |
| 15 | `max_tokens=1024` and `max_length` on `reasoning` | `PERF-04` | `evaluator.py` | 5 min |

Step 12 must be done **together** with the `SEC-02` fix: with a pool, `SET app.current_tenant` persists between uses of the same connection and becomes a cross-tenant leak vector if it is not bounded to the transaction. See the note at the end of `PERF-01`.

### Block 4 — Documentation reconciliation

| # | Action | Finding | Files |
|:---:|---|---|---|
| 16 | Decide about streaming: reimplement with `astream_events`, or rewrite the README and flag `TROUBLESHOOTING.md` §4-5 | `DOC-01` | `chat.py` or `README.md` |
| 17 | Add `ge=0.0, le=1.0` to `RAGEvaluation` (aligns the code with the paper) | `DOC-02` | `evaluator.py` |
| 18 | ✅ done (2026-09-16). Rewrite `.env.example`; historical banner in `CONTEXT.md`; in the README, fill in `.env` before starting the database | `DOC-03` | `.env.example`, `CONTEXT.md`, `README.md` |
| 19 | Correct the mention of NetworkX and point to the roadmap | `DOC-04` | `README.md` |
| 20 | Historical-document banner in `ARCHITECTURE.md` | `DOC-05` | `ARCHITECTURE.md` |
| 21 | Align 400/500 tokens; remove `overlap`; cite by function, not by line | `DOC-06` | `PAPER.md` (both languages at the time), `ingestion.py` |
| 22 | A single `ANTHROPIC_MODEL` constant; correct "Claude 3.5 Haiku" | `DOC-07` | new + 7 calls + `README.md` |
| 23 | Align the Python badge with `requires-python` | `DOC-08` | `README.md` or `pyproject.toml` |

### Block 5 — Hygiene and coverage

| # | Action | Finding |
|:---:|---|---|
| 24 | 🟡 in part (2026-11-09): `pyjwt`, `numpy` and `python-multipart` declared; `pytest` and `pytest-asyncio` are already in `dev`. Moving `deepeval` to `dev` is left | `HYG-01` |
| 25 | Delete the 9 dead files and `IngestRequest` | `HYG-02` |
| 26 | Extend `.gitignore`; `git rm --cached .idea uvicorn.log` | `HYG-03` |
| 27 | `datetime.now(timezone.utc)` | `HYG-04` |
| 28 | ✅ done (2026-09-16). Two-layer regression suite (pure logic and disposable Postgres) with a negative control per finding; `test_rag.py` set aside in `tests/evals/` for the evals change | `BUG-07` |

Step 28 has value of its own: unit tests of `route_supervisor` / `route_reviewer` on hand-built dictionaries would catch `BUG-05` as a regression and need neither a database nor the API.

### Effort summary

| Block | Estimated effort | Priority |
|---|:---:|---|
| 1 — Security | ~30 min | **Blocking** |
| 2 — Functional correctness | ~2.5 h | High |
| 3 — Performance | ~3 h | High |
| 4 — Documentation | ~2 h | Medium (high for a portfolio) |
| 5 — Hygiene | ~1.5 h | Medium |
| **Total** | **~9.5 h** | |

---

## 11. Appendix A: Document ↔ Code Traceability Matrix

**Legend:** ✅ verified in the code · ⚠️ partly true or qualified · ❌ divergent

### `README.md`

| Claim | Status | Finding |
|---|:---:|---|
| Real-time SSE streaming with `Instructor` | ❌ | `DOC-01` |
| GraphRAG with NetworkX | ❌ | `DOC-04` |
| Claude 3.5 Haiku | ❌ | `DOC-07` |
| Python 3.12+ | ❌ | `DOC-08` |
| `cp .env.example .env` + `ANTHROPIC_API_KEY` | ❌ | `DOC-03` |
| Reasoning loops with "deeper queries" | ❌ | `BUG-05` |
| Deterministic function calling (3 tools) | ⚠️ | works once; then `BUG-02` |
| Multi-tenancy through RLS | ⚠️ | implemented, defeated by `SEC-01` |
| Semantic cache (`cos_distance < 0.15`) | ⚠️ | equivalent to similarity ≥ 0.85; different wording |
| Two-stage retrieval (RRF + cross-encoder) | ✅ | — |
| Semantic chunking by iterative cosine similarity | ✅ | divergent constant (`DOC-06`) |
| HyDE and Multi-Query in the supervisor | ✅ | — |
| LLM-as-a-judge evaluator on 3 dimensions | ✅ | `DOC-02`, `PERF-04` on its robustness |
| Traceability with Langfuse (`@observe`) | ✅ | 12 instrumented functions |

### `PAPER.md` (Spanish and English versions at the time)

| Section | Claim | Status | Finding |
|---|---|:---:|---|
| §5.1 | RRF with $k=60$, `FULL OUTER JOIN` fusion, `top_k=15` | ✅ | cited lines out of date (`DOC-06`) |
| §5.2 | $L_{max} = 500$ tokens | ❌ | `DOC-06` |
| §5.2 | Threshold $\tau = \mu + 1.25\sigma$ | ✅ | — |
| §5.2 | Cosine distance formula | ✅ | — |
| §5.3 | HNSW `m=16`, `ef_construction=64` | ✅ | pgvector defaults, correct |
| §5.3 | Cache threshold 0.85 | ✅ | — |
| §5.3 | Normalized MiniLM vectors ($\|v\|=1$) | ✅ | — |
| §5.4 | State machine $\mathcal{M}$, bound $\mathcal{O}(2)$ | ⚠️ | the bound is correct; the loop adds no information (`BUG-05`) |
| §5.5 | Deduplication by `content` hash | ✅ | — |
| §5.5 | $\mathcal{O}(\max T_{retrieval})$ "bounded by the `asyncpg` pool" | ❌ | `PERF-01`: there is no pool |
| §5.5 | Naive GraphRAG, 1-hop, `LIMIT 10`, regex `\w+` | ✅ | honest description |
| §5.6 | Pydantic `ge`/`le` constraints in the evaluator | ❌ | `DOC-02` |
| §4.3.1 | The supervisor resolves coreferences | ❌ | `BUG-03` |
| §4.3.2 | The researcher calls no LLM, only concurrency | ✅ | — |
| §4.4 | Multi-tenant isolation through RLS | ⚠️ | defeated by `SEC-01` |
| §8.2 | No systematic benchmarks | ✅ | acknowledged limitation |
| §9.2 | FlashRank model patch because of a 404 | ✅ | `ms-marco-MiniLM-L-12-v2` confirmed |
| §10.1-10.4 | Limitations: monolingual BM25, flat GraphRAG, cache without TTL, no Dockerfile | ✅ | correct and honest |

### `ARCHITECTURE.md`

| Claim | Status | Finding |
|---|:---:|---|
| 256-token chunking / overlap 30 with `tiktoken` | ❌ | `DOC-05` |
| Purely vector retriever | ❌ | `DOC-05` |
| Reranker `ms-marco-TinyBERT-L-2-v2` | ❌ | `DOC-05` |
| Linear 3-phase pipeline | ❌ | `DOC-05` |
| Evals with DeepEval in `tests/` | ❌ | `BUG-07` |
| Pydantic contracts (`SearchResult`, `RerankedResult`, `StructuredAnswer`) | ✅ | still current |
| Instructor patches the Anthropic client with validation retries | ✅ | — |

### `CONTEXT.md`

| Claim | Status | Finding |
|---|:---:|---|
| Stack on OpenAI (`gpt-4o-mini`, `text-embedding-3-small`) | ❌ | `DOC-03` |
| Current status: only `extractor`, `retriever`, `reranker` | ❌ | frozen at Phase 1 |
| Rule: all I/O asynchronous | ⚠️ | `PERF-03` is the exception |
| Rule: instrument with `@observe` | ✅ | 12 functions |
| Rule: zero heavy dependencies | ⚠️ | unused `deepeval` (`HYG-01`) |

### `GRAPHRAG_ARCHITECTURE.md`

| Claim | Status | Finding |
|---|:---:|---|
| `knowledge_graph` table with RLS and `ON DELETE CASCADE` | ✅ | in `apply_graphrag.sql`, not in `01_init.sql` (`BUG-04`) |
| Triple extraction with Instructor + Pydantic | ✅ | — |
| Lowercase normalization | ✅ | `graphrag.py:58` |
| Concurrent ingestion with `asyncio.gather` | ✅ | `ingestion.py:250-251` |
| Seed node extraction by words > 3 letters | ✅ | `SEC-03` on how it is built |
| Injection at index 0 without going through the reranker, with a justification | ✅ | an excellent decision, well argued |
| Change to `chat.py` to inject the subgraph | ⚠️ | it lives in `nodes.py:86-93` today, after the migration |

### `PHASE_4_IMPLEMENTATION_DETAILS.md`

| Claim | Status | Finding |
|---|:---:|---|
| Semantic cache with a 0.85 threshold and an empirical justification | ✅ | poisoned by `BUG-01`, over-applied by `BUG-02` |
| Memory: background extraction, top-3 facts > 0.3 similarity | ✅ | — |
| Facts in the third person, wrapped in `<USER_PROFILE>` | ✅ | — |
| Evaluator as a fire-and-forget `BackgroundTask` | ✅ | `PERF-04`, `DOC-02` on its robustness |
| LangGraph + evaluator sequence diagram | ✅ | faithful to the real flow |

### `TROUBLESHOOTING.md`

| Section | Claim | Status | Finding |
|---|---|:---:|---|
| §1 | Router with the context of Bryan's résumé | ✅ | `router.py:49` |
| §2 | `top_k_rerank` raised from 3 to 7 | ❌ | `BUG-06`: hardcoded to 10 today |
| §2 | Deduplication by `content` and 15 candidates | ✅ | survived the migration |
| §3 | ML model cold start causes refusals | ⚠️ | made 4× worse by `PERF-02`; `BUG-08` is a third cause of the same symptom |
| §4 | Native streaming with `st.write_stream()` | ⚠️ | the frontend still works this way; the backend no longer emits tokens (`DOC-01`) |
| §5 | `data.get("answer") or ""` for partial objects | ✅ | `app.py:115` |
| §6 | `max_tokens` raised to 2048 in the extractor | ✅ | 8192 today; the evaluator did not get the same treatment (`PERF-04`) |

### `PAPER_PLAN.md`

| Section | Claim | Status | Finding |
|---|---|:---:|---|
| §1 | `01_init.sql` is a "unified script" | ❌ | `BUG-04`: `knowledge_graph` and `FORCE` are missing |
| §1 | `.env.example` with the Anthropic and JWT keys | ❌ | `DOC-03` |
| §3.9 | `max_tokens=500` in chunking | ❌ | `DOC-06` |
| §3.4 | The model's default temperature (1.0) | ✅ | no call sets it |
| §3.7 | RRF with $k=60$ | ✅ | — |
| §3.11 | GraphRAG: regex `\w+`, `len>3`, `LIMIT 10` | ✅ | — |
| §5 | Inventory of 6 known limitations | ✅ | correct and honest |

### `ROADMAP_PHASE_5_SCALABILITY.md`

| Epic | Status | Observation |
|---|:---:|---|
| 1 — Full containerization | ✅ | it must take in `BUG-04` (the compose file does not initialize a clean database) and `BUG-08` (the re-ranker model must be baked into the image, not downloaded on every start) |
| 2 — Evaluations dashboard | ✅ | the sample is biased upwards by `PERF-04` |
| 3 — Cache garbage collector | ✅ | requires cleaning up the `BUG-01` rows first |
| 4 — Multilingual BM25 | ✅ | correctly identified |
| 5 — Topological GraphRAG | ✅ | contradicts the README's claim about NetworkX (`DOC-04`) |

---

## 12. Appendix B: System Constants and Thresholds

An inventory of every numeric value that governs behavior, with its location and documentation status.

| Constant | Value | Location | Documented in | Status |
|---|:---:|---|---|:---:|
| Embedding dimension | 384 | `sql/01_init.sql:7` + 4 services | `PAPER.md` §5.3 | ✅ |
| Embedding model | `all-MiniLM-L6-v2` | 4 files | `README.md`, `PAPER.md` | ✅ |
| Re-ranking model | `ms-marco-MiniLM-L-12-v2` | `reranker.py:10` | `PAPER.md` §9.2 | ✅ (`ARCHITECTURE.md` ❌) |
| Re-ranker cache | `/tmp/flashrank` | `reranker.py:10` | — | ❌ `BUG-08` |
| LLM model | `claude-haiku-4-5-20251001` | 7 calls | `README.md` says 3.5 | ❌ `DOC-07` |
| RRF constant $k$ | 60 | `retriever.py:54` | `PAPER.md` §5.1 | ✅ |
| FTS dictionary | `'spanish'` | `retriever.py:44,46,47`, `01_init.sql:9` | `PAPER.md` §10.1 | ✅ (acknowledged limitation) |
| Retrieval `top_k` | 15 | `nodes.py:70` (hardcoded) | `PAPER.md` §5.1 | ⚠️ `BUG-06` |
| Re-ranking `top_k` | 10 | `nodes.py:83` (hardcoded) | the contract says 7 | ❌ `BUG-06` |
| Break multiplier $c$ | 1.25 | `ingestion.py:78` | `PAPER.md` §5.2 | ✅ |
| Chunk `max_tokens` | 400 | `ingestion.py:48` | the paper says 500 | ❌ `DOC-06` |
| Chunk `overlap` | 0 (dead) | `ingestion.py:48` | — | ❌ `DOC-06` |
| Cache threshold | 0.85 | `cache.py:16` | `PHASE_4_IMPL` §1, `PAPER.md` §5.3 | ✅ |
| Cache TTL | — (none) | — | `ROADMAP` §3 | ✅ (acknowledged as pending) |
| Memory threshold | 0.3 | `memory.py:89` | `PHASE_4_IMPL` §2 | ✅ |
| Memory top-K | 3 | `memory.py:66` | `PHASE_4_IMPL` §2 | ✅ |
| Max. facts per extraction | 3 | `memory.py:19` (prompt) | `PAPER_PLAN` §2 | ✅ |
| Graph edge limit | 10 | `graphrag.py:86` | `PAPER.md` §5.5 | ✅ |
| Min. seed node length | > 3 characters | `graphrag.py:72` | `PAPER.md` §5.5 | ✅ |
| Iteration limit | 2 | `graph.py:13` | `PAPER.md` §5.4 | ⚠️ `BUG-05` |
| History window | 4 messages | `router.py:41` | — | ⚠️ unreachable (`BUG-03`) |
| JWT expiry | 60 min | `auth.py:10` | — | ✅ |
| HNSW `m` / `ef_construction` | 16 / 64 | pgvector defaults | `PAPER.md` §5.3 | ✅ |
| Tool timeout | 5 s | `tools.py:16,32` | `PAPER_PLAN` §2 | ✅ |
| Postgres port | 5433 → 5432 | `docker-compose.yml:8` | `README.md` | ✅ |

---

## 13. Appendix C: Inventory of LLM Calls

Seven calls, all through `instructor.from_anthropic(AsyncAnthropic(...))` except the vision one.

| # | Function | File:line | `response_model` | `max_tokens` | When | Notes |
|:---:|---|---|---|:---:|---|---|
| 1 | `analyze_query` | `router.py:74` | `QueryIntent` | 500 | Synchronous (supervisor) | History always empty (`BUG-03`) |
| 2 | `generate_answer` | `extractor.py:41` | `StructuredAnswer` | 8192 | Synchronous (generator) | After `DOC-01`, only as the fallback |
| 3 | `generate_answer_stream` | `extractor.py:76` | `Partial[StructuredAnswer]` | 8192 | **Never** | Dead code (`DOC-01`); fixed: today it is the generator's normal path |
| 4 | `extract_and_save_facts` | `memory.py:36` | `ExtractedFacts` | 200 | Background | Exceptions swallowed |
| 5 | `extract_knowledge_graph` | `graphrag.py:35` | `KnowledgeGraphExtraction` | 1024 | Ingestion (per chunk) | Exceptions swallowed |
| 6 | `evaluate_rag_response` | `evaluator.py:58` | `RAGEvaluation` | 300 | Background | `PERF-04`, `DOC-02` |
| 7 | `describe_image_with_claude` | `ingestion.py:117` | — (plain text) | 1000 | Ingestion (per image) | The only one without Instructor; a client instantiated per call |

**Cross-cutting observations.**

- **No call sets `temperature`**, so all use the model's default (1.0). For classification (#1), structured extraction (#4, #5) and evaluation (#6) tasks, a low temperature (0.0–0.2) would give more stable and reproducible results. `PAPER_PLAN.md` §3.4 documents it as a decision, but does not justify why it is the right one for deterministic tasks.
- **`describe_image_with_claude` instantiates a new `AsyncAnthropic` on every call** (`ingestion.py:113`), unlike the other six, which reuse a module-level client. A PDF with 20 images means 20 clients created and discarded.
- **Cost per complex query:** 3 LLM calls on the normal path (router + generator + evaluator) plus 1 for memory in the background = **4**. With the `BUG-05` loop: **5**.

---

## 14. Appendix D: Inventory of System Prompts

The six prompts that govern behavior, with their exact location for review.

| Agent | Location | Role | Approx. length |
|---|---|---|:---:|
| **Router / Supervisor** | `router.py:48-70` | Classifies into 4 intents; generates 3 Multi-Query variants and 1 HyDE document | 23 lines |
| **Generator** | `extractor.py:26-37` | Answers only from the context; cites by ID; flags `requires_more_info` | 12 lines |
| **Generator (stream)** | `extractor.py:64-73` | The same + the anti-plain-text instruction from `TROUBLESHOOTING.md` §6 | 10 lines |
| **Graph extractor** | `graphrag.py:26-33` | Extracts triples (source, relation, target) | 8 lines |
| **Memory extractor** | `memory.py:28-33` | Extracts persistent facts in the third person, max. 3 | 6 lines |
| **Evaluator** | `evaluator.py:40-55` | Impartial judge; 3 metrics from 0.0 to 1.0 + reasoning | 16 lines |
| **Image describer** | `ingestion.py:115` | Describes an image in detail for RAG; extracts visible text | 1 line |

**Observations.**

- The router's prompt (`router.py:49`) hardcodes the domain as a constant: *"an AI Engineer Sandbox that is currently analyzing the résumé and professional profile of the engineer Bryan Bobadilla"*. It is the solution documented in `TROUBLESHOOTING.md` §1 and it works, but it ties the system to one specific use case: any tenant that ingests another kind of document gets a router biased towards a résumé that is not theirs. In a real multi-tenant system, that context should be derived from the tenant's corpus.
- The generator's prompt (`extractor.py:26-37`) **does not include** the anti-plain-text instruction that the streaming version does have (`extractor.py:67`), even though `TROUBLESHOOTING.md` §6 documents that failure as a general Haiku behavior with requests for long analyses. Since the streaming version is dead (`DOC-01`), **the instruction that fixed the bug is not applied on the only active path**. It is a finding derived from `DOC-01` that is best fixed together with it. **Fixed (2026-09-13):** both generators now share `_build_prompt()`, so the instruction applies to both and cannot drift apart again.
- Every prompt goes in the `user` turn; none uses the Anthropic API's `system` parameter, which is the canonical place for role instructions and enables prompt caching when the content is stable. For the router and the evaluator, whose instructions are identical on every call, it would be a direct cost and latency optimization.

---

## 15. Appendix E: Verification Commands

Full reproduction of the findings without running the system.

```bash
# --- Security ---
grep -n "SECRET_KEY\|password123" src/api/auth.py            # SEC-01
grep -n "tenant_id: str" src/api/auth.py                      # SEC-02
grep -rn "SET app.current_tenant" src/ | wc -l                # SEC-02 → 9
sed -n '69,89p' src/services/graphrag.py                      # SEC-03
sed -n '20,27p' src/api/routers/ingest.py                     # SEC-04

# --- Functional defects ---
sed -n '112,124p' src/api/routers/chat.py                     # BUG-01
grep -n "intent_type" src/api/routers/chat.py                 # BUG-02 → none
grep -rn "history" src/ | grep -v "^src/frontend"             # BUG-03
ls sql/ | sort && grep -n "app_user" sql/*.sql                # BUG-04
grep -c "knowledge_graph\|FORCE" sql/01_init.sql              # BUG-04 → 0
sed -n '11,18p' src/services/agent_graph/graph.py             # BUG-05
grep -rn "top_k_retrieve\|top_k_rerank" src/                  # BUG-06 → only the definition
grep -n "retrieve_documents(query" tests/test_rag.py          # BUG-07
sed -n '76,83p' .venv/lib/*/site-packages/flashrank/Ranker.py  # BUG-08 (directory check)
ls -la /tmp/flashrank/*/                                      # BUG-08 (empty directories)

# --- Performance ---
grep -rn "create_pool" src/                                   # PERF-01 → none
grep -rn "asyncpg.connect" src/ | wc -l                       # PERF-01 → 9
grep -rn "SentenceTransformer(" src/                          # PERF-02 → 4
grep -n "model.encode" src/services/ingestion.py              # PERF-03
grep -n "max_tokens" src/services/*.py                        # PERF-04

# --- Documentation divergences ---
grep -rn "generate_answer_stream" src/                        # DOC-01 → only the definition
grep -n "ge=\|le=" src/services/evaluator.py                  # DOC-02 → none
cat .env.example && grep -rn "OPENAI" src/                    # DOC-03
grep -rn "networkx" src/ pyproject.toml                       # DOC-04 → none
grep -n "max_tokens\|overlap" src/services/ingestion.py       # DOC-06
grep -rn "claude-haiku" src/ | wc -l                          # DOC-07 → 7
grep -n "requires-python" pyproject.toml                      # DOC-08

# --- Hygiene ---
grep -iE "jwt|numpy|multipart" pyproject.toml                 # HYG-01 → none
ls *.py                                                       # HYG-02 → 6 scripts
git ls-files | grep -E "\.idea|\.log"                         # HYG-03
grep -n "utcnow" src/api/auth.py                              # HYG-04
```

---

## 16. Closing note

The 28 findings come down to three root causes, and they are worth naming because they explain the pattern better than the list does:

1. **The migration to LangGraph (Phase 4) was surgical in the code and did not carry over to the documentation.** The graph works; what was left behind are the pieces of the previous pipeline that nobody disconnected (`DOC-01`, `BUG-03`, `BUG-06`) and the documents that described the replaced flow (`DOC-05`, parts of `TROUBLESHOOTING.md`).

2. **The development environment was never reproduced from scratch.** `BUG-04`, `BUG-08`, `DOC-03` and part of `HYG-01` stem from it being built incrementally by hand: the SQL scripts were run in logical order on an existing database, and the re-ranker cache was downloaded once into a volatile directory. That state works on the author's machine and is fragile or nonexistent on any other.

3. **The papers were written describing the intended system, not the one that runs.** `DOC-02` and the pool claim in `PERF-01` are the two clearest. The mathematical formalization is rigorous and mostly faithful; the divergences show up in the claims about implementation.

None of the three questions the design. Once blocks 1 to 3 are applied, the system does what the documentation says it does, and what the documentation says is genuinely advanced.
