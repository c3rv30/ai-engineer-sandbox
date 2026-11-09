## Why

The regression suite (`regression-test-suite`) left the HTTP edge out. Five fixes still have no test protecting them, among them the audit's two 🔴 findings: `SEC-01` (token signed with another key), `SEC-02` (malformed `tenant_id` in the token), `SEC-06` (the exception text reached the client), `BUG-01` (the cache stored the answer polluted with the progress messages) and `BUG-09` (`/chat/stream/` returned no answer for greetings, out-of-scope topics or tools). Today their only proof lives in commit messages and in the audit, so reintroducing any of them breaks nothing.

## What Changes

- Third layer of the suite, `tests/api/`: the full FastAPI application with `TestClient`, and doubles instead of the graph and the data services.
  - **Real authentication, no doubles:** the `SEC-01` and `SEC-02` 401s are checked with the real `get_current_user`.
  - **Doubles:** `agent_graph` (`ainvoke` and `astream`), `check_semantic_cache`, `save_semantic_cache`, `retrieve_user_facts`, `extract_and_save_facts` and `evaluate_rag_response`, replaced in the namespace of `src/api/routers/chat.py`. The layer does not connect to Postgres or call any LLM, and **does not need Docker**.
- Regressions covered: 401 for a token with another key, without `sub` or without `tenant_id`, and for a malformed `tenant_id` (`SEC-01`, `SEC-02`); the API does not start without `JWT_SECRET_KEY` or with one that is too short (`SEC-01`); a generic message with an identifier on an internal failure, at all three points, and messages written for the client that are kept (`SEC-06`); the object sent to be stored in the cache is clean, while the one the client gets carries the progress (`BUG-01`); the stream returns an answer for greetings, out-of-scope topics and tools (`BUG-09`).
- `api` marker and selection by directory, like the other layers. The layer is part of the default `uv run pytest` run.
- Negative control per finding, as in the previous change: each defect is reintroduced, at least one test is checked to fail and it is restored.
- Status of the five findings in `docs/TECHNICAL_AUDIT.md`: all are already fixed, so what is noted is that they now have automatic regression tests.

## Capabilities

### New Capabilities
_None._

### Modified Capabilities
- `regression-test-suite`: adds the API layer requirements (how it runs and which doubles it uses) and those of the five HTTP edge regressions. The existing requirements do not change.

## Impact

- **Production code:** none planned. `agent_graph` and the services are already module names in `src/api/routers/chat.py`, so they are replaced from the test. If, while implementing it, a point showed up that cannot be doubled without touching production, it is decided before changing anything.
- **Tests and configuration:** `tests/api/` (new, with its `conftest.py` and its doubles) and `pyproject.toml` (`api` marker).
- **Suite time:** the full run goes from ~8 s to ~18 s, because importing the application loads the embedding model and the re-ranker (~10 s, once per run). `uv run pytest tests/unit` stays at ~0.3 s.
- **Documentation:** `docs/TECHNICAL_AUDIT.md`.
- **Out of scope:** the quality evals and what the README says about them; end-to-end ingestion (`SEC-04` already has its layer 1 test); the performance and Docker measurements, which remain manual; and layer 2 of `SEC-07` (neutralizing `search_path` in the application), which is a separate decision.
