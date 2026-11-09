## Why

The repository has no runnable test (`BUG-07`). The only suite, `tests/test_rag.py`, fails with a `TypeError` before evaluating anything. Even if it were fixed, it would need an OpenAI judge that is not configured, and it would ask about a document that is not in the corpus. Meanwhile, the audit remediation has closed more than twenty findings, and each fix was verified with a negative control from throwaway scripts that no longer exist: nothing stops those defects from coming back. That regression net is needed before touching the code any further (`HYG-05`, layers 2 and 3 of `SEC-07`, API with doubles).

## What Changes

- New regression suite in `tests/`, organized in two layers:
  - **Layer 1, pure logic:** no database, no LLM, no `.env` and no model loading. It covers the cache policy (`BUG-02`, `BUG-06`, `BUG-10`), the retrieval window, exhaustion and the reviewer's route (`BUG-05`), history formatting (`BUG-03`), file name sanitizing (`SEC-04`), the tenant signature (`SEC-05`) and the evaluator's score bounds (`DOC-02`).
  - **Layer 2, real and disposable Postgres:** a database started by the suite itself from an empty volume. It covers isolation with a signed context (`SEC-05`), the GraphRAG query against an injection payload (`SEC-03`), the tenant not surviving in the pool (`PERF-01`), `app_user`'s privileges (`HYG-07`, `SEC-07`) and bootstrapping from scratch (`BUG-04`).
- Pure functions are extracted from modules that load models or create clients when imported. They move without changing behavior, and the original modules import them from the new place:
  - the cache policy, from `src/api/routers/chat.py`;
  - `retrieval_window`, the exhaustion decision (inline in `researcher_node` today) and `route_reviewer`, from `src/services/agent_graph/`;
  - the origin name sanitizing (inline in `ingest_endpoint` today);
  - the `RAGEvaluation` model, from `src/services/evaluator.py`.
- pytest configuration: collection limited to `tests/`, `pytest-asyncio` and markers to select layers. Without Docker, layer 2 **fails**; it is not skipped.
- `pytest` and `pytest-asyncio` move to development dependencies.
- `tests/test_rag.py` is not fixed here: it is marked as an eval and excluded from the default run, until the evals change.
- The `BUG-07` entry in `docs/TECHNICAL_AUDIT.md` gets its status line, with the correction that the minimal patch proposed no longer applies.

## Capabilities

### New Capabilities
- `regression-test-suite`: what the regression suite must prove, how each layer runs and what guarantees it gives about the development database and the environment.

### Modified Capabilities
_None: there are no previous specs and the extractions do not change the application's observable behavior._

## Impact

- **Production code (moves only):** `src/api/routers/chat.py`, `src/api/routers/ingest.py`, `src/services/agent_graph/nodes.py`, `src/services/agent_graph/graph.py`, `src/services/evaluator.py`, plus the new modules that receive what is extracted.
- **Tests and configuration:** `tests/` (new suite, `conftest.py`, fixtures) and `pyproject.toml` (pytest configuration, development group).
- **Test infrastructure:** Docker becomes a requirement for the full suite. Layer 2 uses its own Compose project, with its own port and volume, which it deletes by exact name at the end. It never touches the development database or its `ai_engineer_sandbox_pgdata` volume.
- **Documentation:** `docs/TECHNICAL_AUDIT.md` (status of `BUG-07`). The README is not touched here: its claim of *"deterministic evals (DeepEval)"* belongs to the evals change.
- **Out of scope:** the API layer with doubles (`SEC-01`, `SEC-02` at the edge, `SEC-06`, `BUG-01`, `BUG-09`), which will be the next change; quality evals with an LLM judge; performance measurements and Docker checks (`PERF-02` to `PERF-04`, `DOC-01`, `HYG-06`, `HYG-08`, `DOC-03`), which remain manual; and the loose scripts in the root (`HYG-02`).
