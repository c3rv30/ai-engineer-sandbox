## Context

See `proposal.md` (Why) and the `regression-test-suite` spec for the requirements. This document only records the constraints of the current code that shape the design.

- **Importing the pure logic costs ~10 s.** Measured on 2026-09-16: `src.services.agent_graph.nodes` takes 8.9 s and `src.api.routers.chat` 9.9 s, because they pull in `sentence_transformers`, `flashrank`, `anthropic`, `langgraph` and `asyncpg`. `src.services.history` and `src.models.requests` take ≤ 0.1 s. `graph.py` imports `nodes.py`, so `route_reviewer` pays that cost too.
- **There is pure logic written inline.** The `BUG-05` exhaustion decision is inside `researcher_node`, and the `SEC-04` name sanitizing, inside `ingest_endpoint`.
- **`src/services/db.py` pins the database at import time.** `DB_DSN` is read once, with `load_dotenv()` and a default pointing to the development database (`localhost:5433`). A test that imports `db.py` before the environment points to the test database leaves the process connected to development, and no error gives it away.
- **The pool is one per event loop** (`PERF-01`), with `DB_POOL_MIN_SIZE=5` by default. By default, pytest-asyncio gives each test a new loop.
- **The packages `src/api/`, `src/api/routers/` and `src/services/agent_graph/` have empty `__init__.py` files**, and `src/`, `src/services/` and `src/models/` have none. A new module inside any of them does not pull in imports through the package.
- **`tests/test_rag.py` imports `deepeval` and the services at module level.** Deselecting it with a marker is not enough, because pytest imports it when collecting it.
- The project uses `uv` (`uv.lock`, README), and `pytest` is currently listed among the production dependencies.

## Goals / Non-Goals

**Goals:**
- That the separation between the pure layer and the database layer is structural, not a convention: it is guaranteed with directories, an import test and a DSN guard.
- That the database layer cannot reach the development database by accident, neither through import order nor through the `.env`.
- Move logic without changing its behavior, with the new tests as proof.

**Non-Goals:**
- Solving `HYG-05`. The pure modules simply do not create clients, and the services stay as they are.
- Parallelizing the suite, measuring coverage or setting up continuous integration.
- Automating the negative control (mutation testing). It is done by hand when writing each test (see D8).

## Decisions

### D1. Layers by directory: `tests/unit/`, `tests/db/` and `tests/evals/`
The layer is decided by the directory, and a `conftest.py` automatically marks everything in `tests/db/` as `db`. The pure layer runs with `uv run pytest tests/unit`, and the full suite with `uv run pytest`.
- *Rejected alternative: markers only (`-m "not db"`).* Even deselected, pytest would import the modules in `tests/db/`, and a single module-level import would be enough to load models or pin the DSN. The directory prevents it without relying on discipline.

### D2. Where the extracted functions go
| Logic | New module | Imported from there by |
|---|---|---|
| `CACHEABLE_INTENTS`, `MIN_CACHE_CONFIDENCE`, `is_cacheable`, `uses_default_retrieval`, `is_cache_eligible` | `src/services/cache_policy.py` | `src/api/routers/chat.py` |
| `retrieval_window`, the exhaustion decision (a new function with the expression that is inline today), `route_supervisor`, `route_reviewer` | `src/services/agent_graph/routing.py` | `nodes.py`, `graph.py` |
| Origin name sanitizing | `src/services/filenames.py` | `src/api/routers/ingest.py` |
| `RAGEvaluation` | `src/models/evaluation.py` | `src/services/evaluator.py` |

The new modules may only import from the standard library, `pydantic` and `src.models.*`. The public names are kept, and the original modules re-export them by importing them, so nothing that already uses them breaks.
- *Rejected alternative: lazy imports inside the current modules.* It would mean touching many more lines and would leave the pure functions in heavy modules.
- *Rejected alternative: `src/api/policies.py` for the cache policy.* That policy does not belong to the HTTP edge: the day another entry point uses the cache, it will need it without FastAPI.

### D3. Guard test for the purity of layer 1
A test in `tests/unit/` imports every pure module in a clean subprocess and checks that `sys.modules` contains neither `sentence_transformers`, `flashrank`, `anthropic` nor `langgraph`. That way, the *No model loading* scenario no longer depends on nobody adding a heavy import.
- *Rejected alternative: measuring import time.* It is fragile and indirect.

### D4. Lifecycle of the disposable database
A session fixture in `tests/db/conftest.py`:
1. Uses the fixed-name Compose project `sandbox_tests`, with `--project-directory` on the repository and an override generated in a temporary directory: port `127.0.0.1:5439`, `restart` reset and the volume of the repository's compose file (which becomes `sandbox_tests_pgdata`).
2. **Before starting**, removes the leftovers of an interrupted run: `down` of the `sandbox_tests` project and deletion of the `sandbox_tests_pgdata` volume, by exact name.
3. `up --wait`. If it fails (no Docker, port taken, broken init script), it calls `pytest.fail` with Compose's output. Never `skip`.
4. In the finalizer, no matter what: `down` and deletion of the volume by exact name, checking first that the volume belongs to the `sandbox_tests` project.

The fixed name prevents two simultaneous runs, but guarantees that a killed run leaves no orphaned volumes: the next one cleans them up.
- *Rejected alternative: a random name per run.* It allows parallelism, but a killed run leaves a volume nobody recognizes, and cleaning it up would mean deleting by prefix, which is exactly the risky pattern the verification notes warn against.
- *Rejected alternative: testcontainers.* It adds a dependency and does not reuse `docker-compose.yml` or the `sql/` scripts, which are what `BUG-04` must prove.

### D5. The environment is set before any import of `src`
`tests/conftest.py` (the root one, which pytest loads before any test) sets in `os.environ`:
- `DATABASE_URL=postgresql://app_user:apppassword@127.0.0.1:5439/postgres`;
- `TENANT_SIGNING_KEY`, generated randomly for the run and also passed to Compose, which gives the environment precedence over the `.env`;
- `JWT_SECRET_KEY`, random;
- `DB_POOL_MIN_SIZE=1`.

Since `load_dotenv()` does not overwrite existing variables, the repository's `.env` stops having any influence. In addition, the database session fixture **checks that `src.services.db.DB_DSN` points to port 5439** and aborts the session otherwise (for example, if something imported `db.py` before the conftest).
- *Rejected alternative: patching `DB_DSN` in the fixture.* It leaves a window in which an early import has already connected to development, and it hides the problem instead of detecting it.

### D6. Pool and event loop in layer 2
The async tests in `tests/db/` share a single session event loop (pytest-asyncio with `loop_scope="session"`), and the session fixture closes the pool with `close_pool()` at the end. That way, `get_pool()` creates a single pool for the whole layer, as in production, and the `PERF-01` test exercises real connection reuse.
- *Rejected alternative: one loop per test.* It would create a pool per test without closing the previous ones, and exhaust connections much like the original `PERF-01` symptom.

### D7. Test data
Each test seeds what it needs as superuser (`postgres`, which bypasses RLS) in the disposable database, with tenants of its own (`aaaaaaaa-…` and `bbbbbbbb-…`) and made-up values impossible to guess, and always checks as `app_user` through the real code (`tenant_connection`, `retrieve_subgraph`). The database is recreated on every run, so there is no need to purge between runs. Within a run, each test uses its own values so as not to depend on the order.

### D8. Negative control when writing each test
For each finding, the previous behavior is reintroduced temporarily. Depending on the case, the previous version of the function is restored with `git show <commit>^:<path>`, or the previous SQL (`GRANT ALL ON DATABASE`, `ALTER DEFAULT PRIVILEGES`, a policy without a signature) is run in the disposable database. It is checked that the test fails, the change is undone and the result is noted in `tasks.md` and in the commit message. No permanent tooling is left behind.

### D9. Dependencies and pytest configuration
- `pyproject.toml`: `pytest` leaves `dependencies` and enters, together with `pytest-asyncio`, `[dependency-groups] dev`. `deepeval` stays where it is until the evals change.
- `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `db` and `eval` markers declared with `--strict-markers`, and an explicit `asyncio_default_fixture_loop_scope`.
- `tests/test_rag.py` moves to `tests/evals/`. `tests/conftest.py` adds `tests/evals/` to `collect_ignore_glob` unless `--run-evals` is passed. That way `deepeval` is not imported in the default run.

## Risks / Trade-offs

- **[A move changes behavior without anyone noticing]** → Layer 1 tests are first written against the function where it is now, with the heavy import, and run again after moving it: same results. Afterwards, the old imports still resolve, and a real API start with a request checks it.
- **[Port 5439 is taken]** → `up --wait` fails and the session ends in `pytest.fail` with Compose's output, which names the port (see Open Questions).
- **[A `kill -9` leaves the test database running]** → It is cleaned up at the start of the next run (D4, step 2). Nothing outside the `sandbox_tests` project is ever affected.
- **[Layer 2 adds ~15 s per run]** → Accepted: the freshly created database is the point. For fast iteration there is `tests/unit`.
- **[Docker becomes a requirement for the full suite]** → Decision confirmed: failing is better than a silently skipped layer.
- **[`graphrag.py` creates an Anthropic client without a key at import time (`HYG-05`)]** → It does not affect `retrieve_subgraph`, which does not call the LLM. If a future SDK version validates the key when building the client, the test will show it as an import error and it will be handled with `HYG-05`.

## Migration Plan

There is no deployment. The order of work is designed so each step can be verified on its own (details in `tasks.md`): pytest configuration and dependencies → layer 1 tests against the current code → extractions, one per finding, with the tests green before and after → purity guard → disposable database fixture → layer 2 tests → negative control of each finding → status in the audit. Undoing means reverting the commits: the extractions are moves with re-exports.

## Open Questions

- Whether the test database port is made configurable from the start or only when it clashes with something. It changes neither the spec nor the tasks.
