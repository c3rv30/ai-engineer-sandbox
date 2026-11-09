## 1. pytest configuration and dependencies

- [x] 1.1 In `pyproject.toml`, take `pytest` out of `dependencies` and create `[dependency-groups] dev` with `pytest` and `pytest-asyncio`, using `uv remove`/`uv add --dev` and `--no-sync` (never `uv sync`: it would uninstall `pyjwt`, which is not declared, `HYG-01`); verify that `uv run pytest --version` answers and that the `.venv` keeps `pyjwt`
- [x] 1.2 Add `[tool.pytest.ini_options]` with `testpaths = ["tests"]`, the `db` and `eval` markers, `--strict-markers` and pytest-asyncio's `loop_scope` (design D9); verify that `uv run pytest --collect-only` collects no `test_*.py` from the root
- [x] 1.3 Create `tests/unit/`, `tests/db/` and `tests/evals/`, move `tests/test_rag.py` to `tests/evals/` and exclude it from collection unless `--run-evals` is passed (D9); verify that `uv run pytest --collect-only` does not import `deepeval` and that `--run-evals` does collect it
- [x] 1.4 Create `tests/conftest.py`, which sets `DATABASE_URL` (port 5439), random `TENANT_SIGNING_KEY` and `JWT_SECRET_KEY` and `DB_POOL_MIN_SIZE=1` before any import of `src` (D5); verify with a temporary test that `src.services.db.DB_DSN` points to 5439 even with the development `.env` present

## 2. Layer 1 against the current code

- [x] 2.1 Write the cache policy tests in `tests/unit/` (spec: *Cache policy regression*), importing from `src.api.routers.chat`; verify that they pass
- [x] 2.2 Write the tests of the retrieval window and of `route_reviewer` (spec: *Self-correction loop regression*, except *Exhausted corpus* and *Saturated window*, which depend on the extraction in 3.3), importing from `nodes.py` and `graph.py`; verify that they pass
- [x] 2.3 Write the `format_history` tests (spec: *Conversation history regression*); verify that they pass
- [x] 2.4 Write the bounds test of `RAGEvaluation` (spec: *Evaluator score bounds regression*), importing from `src.services.evaluator`; verify that it passes
- [x] 2.5 Write the `sign_tenant` test against an HMAC-SHA256 computed in the test itself with the standard library; verify that it passes (the comparison with the database's HMAC is done in 6.1)

## 3. Extractions without behavior change

- [x] 3.1 Move the cache policy to `src/services/cache_policy.py` and have `chat.py` import it from there (D2); verify that the tests from 2.1, pointing at the new module, give the same results and that `from src.api.routers.chat import is_cache_eligible` still works
- [x] 3.2 Move `retrieval_window`, `route_supervisor` and `route_reviewer` to `src/services/agent_graph/routing.py`, imported from `nodes.py` and `graph.py`; verify that the tests from 2.2, pointing at the new module, give the same results
- [x] 3.3 Extract to `routing.py` the exhaustion decision that is inline in `researcher_node` today, as a function with the same inputs (result sizes, unique candidates, current window and base), and use it from `researcher_node`; write the *Exhausted corpus* and *Saturated window* scenarios and verify that they pass
- [x] 3.4 Extract the origin name sanitizing to `src/services/filenames.py` and use it from `ingest_endpoint`; write the *Ingestion file name regression* tests (with `/`, `\` and `..`) and verify that they pass
- [x] 3.5 Move `RAGEvaluation` to `src/models/evaluation.py`, imported from `evaluator.py`; verify that the test from 2.4, pointing at the new module, passes
- [x] 3.6 Start the real API against the development database, ask one knowledge question with history and another without, and check that they answer and that the cache is used only by the second; also verify that the development database is left with the initial counts (purging whatever the request and its background tasks write)

## 4. Purity of layer 1

- [x] 4.1 Write the guard test (D3): it imports, in a clean subprocess, every module `tests/unit/` uses and checks that `sys.modules` contains neither `sentence_transformers`, `flashrank`, `anthropic` nor `langgraph`; verify that it passes and that it fails if `import src.services.agent_graph.nodes` is added to the list
- [x] 4.2 Run `uv run pytest tests/unit` in a clean clone, without `.env` and with Docker stopped; verify that everything passes in seconds (spec: *Clone without configuration* and *Explicit selection of the pure layer*)

## 5. Disposable database

- [x] 5.1 Write in `tests/db/conftest.py` the session fixture with the D4 lifecycle (prior cleanup by exact name, `up --wait`, `pytest.fail` if it fails, `down` and volume deletion in the finalizer) and the automatic `db` marking; verify that after a run neither a container nor a `sandbox_tests*` volume remains
- [x] 5.2 Add the DSN guard (D5) to the fixture; verify that it aborts the session if `DB_DSN` does not point to 5439 (forcing it in a temporary test)
- [x] 5.3 Configure the session event loop and the pool closing (D6); verify with `pg_stat_activity` during a run that `app_user` connections do not grow with the number of tests
- [x] 5.4 Verify the cleanup after a failure and after an interruption: with a test that fails on purpose and with a `kill -9` in the middle of a run, the next run starts clean and nothing remains at the end
- [x] 5.5 Verify the failure without Docker (spec: *Docker not available*): with Docker stopped, `uv run pytest` ends in failure, and the message says the test database could not be started

## 6. Layer 2

- [x] 6.1 Write the *Tenant isolation regression* tests: valid signed context (with a positive control), no signature, fake signature and tenant rewritten from the statement, through `tenant_connection`; complete the *Matching signature* scenario by comparing `sign_tenant` with the HMAC computed by the database; verify that they pass
- [x] 6.2 Write the GraphRAG injection test: seed relations in two tenants and call `retrieve_subgraph` with the `SEC-03` payload from the tenant without them, with a positive control from the owner; add, with a permissive tokenizer, the tautology and the apostrophe (scenario *Question words as data*, added during implementation: the cross-tenant read is already blocked by `SEC-05` and on its own would not catch the return of `SEC-03`); verify that they pass
- [x] 6.3 Write the test of the connection reused from the pool (`PERF-01`), forcing the second operation to get the same physical connection, and the *Transaction-local context* one with a pool without reset (added during implementation: asyncpg's `RESET ALL` would hide a `set_config(..., false)`); verify that they pass
- [x] 6.4 Write the *Application role privileges regression* tests (new table, `CREATE SCHEMA`, the role's stored settings, signing key); verify that they pass
- [x] 6.5 Verify that the development database is not touched: counts 22/128/4/3/0 and the same `ai_engineer_sandbox_pgdata` volume before and after `uv run pytest` with the development database running

## 7. Negative control per finding

- [x] 7.1 For each layer 1 finding (`BUG-02`, `BUG-06`, `BUG-10`, `BUG-05`, `BUG-03`, `SEC-04`, `DOC-02`), reintroduce the previous behavior (D8), check that at least one test of that finding fails and undo; note here which test failed in each case
- [x] 7.2 For each layer 2 finding (`SEC-05`, `SEC-03`, `PERF-01`, `HYG-07`, `SEC-07`), reintroduce the previous SQL or code in the disposable database or in the code (D8), check that at least one test fails and undo; note here which test failed in each case
- [x] 7.3 Check the *Freshly created database* scenario (`BUG-04`) by temporarily breaking the order of the `sql/` scripts: the session must end in `pytest.fail`; undo

### Negative control results (2026-09-16)

Each mutation was applied to the code or to `sql/`, the corresponding layer was run and the change was restored with `git checkout` (clean tree at the end; 0 test containers and 0 test volumes after each run).

| Finding | Behavior reintroduced | Tests that fail |
|---|---|---|
| `BUG-02` | cache any answer (before `1a35a4d`) | 10: non-cacheable intent, insufficient or missing confidence, no field, asks for more information |
| `BUG-02` | only remove the intent allowlist | 5: non-cacheable intent |
| `BUG-06` | the cache ignores custom `top_k` | 3: custom parameters do not use the cache |
| `BUG-06` | `top_k_retrieve` without `ge`/`le` | 3: out-of-range parameters |
| `BUG-10` | the cache ignores the history (before `e0fbdfc`) | 1: request with history does not use the cache |
| `BUG-05` | the window does not widen (before `993163e`) | 7, including widening per retry and saturated window |
| `BUG-05` | the reviewer ignores `retrieval_exhausted` | 1: no retry if the search is exhausted |
| `BUG-05` | never considered exhausted | 3: exhausted corpus, no variants, saturated window |
| `BUG-05` | widening without a cap at the maximums | 6: cap at the maximums, stalls, saturated window |
| `BUG-03` | the history is discarded (original defect) | 2: turn window, malformed turns |
| `BUG-03` | no turn window | 1: turn window |
| `BUG-03` | `msg["role"]` without tolerating malformed turns | 3: malformed turns, unusable history |
| `SEC-04` | client name as is (before `0ae8cc5`) | 8: last component, no separators |
| `SEC-04` | `basename` without normalizing `\` | 2: last component, no separators |
| `DOC-02` | scores without `ge`/`le` (before `4e9cde2`) | 6: out-of-range score |
| `SEC-05` | policies on `current_setting`, without a signature (before `9100c05`) | 5: no signature, fake signature, another tenant's signature, tenant rewritten, freshly created database |
| `SEC-03` | `WHERE` by concatenation (before `1ec35e7`) | 2: tautology, apostrophe. The cross-tenant read does **not** fail: `SEC-05` blocks it, as anticipated |
| `PERF-01` | `set_config(..., false)` in `tenant_connection` | 1: transaction-local context. The real pool test does **not** fail: the `RESET ALL` hides it, as anticipated |
| `HYG-07` | `ALTER DEFAULT PRIVILEGES` back (before `a1a73e2`) | 1: new table in `public` |
| `SEC-07` | `GRANT ALL` on the database (before `535af88`) | 1: cannot create schemas |
| `SEC-07` | stored `ALTER ROLE app_user SET search_path` | 1: no stored settings of its own |
| `BUG-04` | `00_create_app_user.sql` renamed to `02_` | the session ends with code 1: 18 errors, "Could not start the test database with docker compose" |

## 8. Wrap-up

- [x] 8.1 Run the full `uv run pytest` twice in a row; verify that both pass and that no test container or volume remains
- [x] 8.2 Add the `BUG-07` status line in `docs/TECHNICAL_AUDIT.md` (§1 table, entry and plan §10), with the correction that the entry's minimal patch no longer applied, and with the negative control table from 7.1 to 7.3; note in the `HYG-01` entry that `uv sync` today uninstalls `pyjwt` and leaves the API unable to start (checked with `--dry-run` on 2026-09-16)
- [x] 8.3 Make the commits with the measurements in the body, following the project's practice; verify with `git status` that nothing is left uncommitted outside what was decided
