## 1. Layer scaffolding

- [x] 1.1 Declare the `api` marker in `pyproject.toml`; verify that `uv run pytest --markers` lists it and that `--strict-markers` does not complain
- [x] 1.2 Create `tests/api/conftest.py` with the layer's automatic marking and a session fixture that imports the application only once (D8); verify with `uv run pytest tests/api --collect-only` that the tests are marked as `api`
- [x] 1.3 Write `tests/api/doubles.py` with the graph script builder (D2): `ainvoke` returns the final state, and `astream` emits `(mode, chunk)` tuples with the real shape of `nodes.py`, including the generator's `custom` channel and the per-node updates; verify with a minimal test that the stream endpoint produces SSE events from a script
- [x] 1.4 Add to `conftest.py` the fixture that installs the doubles with `monkeypatch` on `src.api.routers.chat` and `src.api.routers.ingest`, and returns the client plus the call record (D1, D5, no context manager); verify that a smoke test gets a 200 without the database running
- [x] 1.5 Write the test that fails if the layer opens a connection to PostgreSQL (D5), watching `asyncpg.connect`; verify that it passes with Docker stopped and that it fails if a test adds a connection on purpose

## 2. Edge authentication (`SEC-01`, `SEC-02`)

- [x] 2.1 401 tests: token signed with another key, token without `sub`, token without `tenant_id` and request without a header; also verify that the graph double was not called in any of them
- [x] 2.2 Malformed `tenant_id` test (including the finding's injection payload) → 401 and no 500; verify that the value does not reach the graph double
- [x] 2.3 Positive control with the real `/auth/token`: a token obtained from the endpoint gets in and reaches the graph with the user's `tenant_id`, typed as a UUID; verify that it passes
- [x] 2.4 Subprocess test of starting without `JWT_SECRET_KEY` and with a key shorter than 32 characters (D4); verify that the message explains the cause and that with a valid key the import works

## 3. Internal error detail (`SEC-06`)

- [x] 3.1 `POST /chat/` test: the graph double raises an exception with a server path in the text; verify that the client gets `Internal error (<id>)`, that the path does not appear and that the log carries the traceback with that same identifier exactly once
- [x] 3.2 `POST /chat/stream/` test: the exception happens during the stream; verify that the delivered event carries the `error` key with the identifier and without the exception text
- [x] 3.3 `POST /ingest/` test: the doubled `ingest_file` raises an exception naming the temporary path; verify the generic message and that the path does not reach the client
- [x] 3.4 Tests of what must be kept: disallowed extension (400 with its message) and graph without a final answer (500 with "The agent graph did not return a final answer."); verify that neither becomes the generic message

## 4. Object stored in the cache (`BUG-01`)

- [x] 4.1 Stream test with a cacheable script: verify that the object the `save_semantic_cache` double receives contains no progress message and matches the structured answer, while the text emitted to the client does carry them
- [x] 4.2 Test that the evaluator double also gets the clean text; verify that it was scheduled as a background task and with which arguments
- [x] 4.3 Test of the path without cache: with history in the request, verify that the cache is neither read nor written (the policy is already covered in layer 1; here it is checked that the endpoint honors it)

## 5. Stream paths (`BUG-09`)

- [x] 5.1 Tests with a script in which the supervisor resolves the request (greeting, out of scope and tool): verify that the last event contains the answer and not just the progress lines
- [x] 5.2 Test with a generator script: verify that the last event contains the full answer exactly once, without duplicating the text emitted token by token
- [x] 5.3 Cache hit test on the stream: verify that a single event is emitted with the cached answer and that the graph never ran

## 6. Negative control per finding

- [x] 6.1 `SEC-01` and `SEC-02`: restore the previous behavior (default key in `auth.py`; `tenant_id` as `str` in `User`), check that at least one test in that section fails and undo; note here which one failed
- [x] 6.2 `SEC-06`: return `str(e)` at the three points, one at a time; check that the corresponding test fails and undo; note here which one failed
- [x] 6.3 `BUG-01`: store the stream object instead of the clean one; check that it fails and undo; note here which one failed
- [x] 6.4 `BUG-09`: do not append the supervisor's answer to the accumulated text; check that it fails and undo; note here which one failed

### Negative control results (2026-09-17)

Each defect was reintroduced in the code, `tests/api` was run and the change was restored with `git checkout` (clean tree at the end).

| Finding | Reintroduced | Tests that fail |
|---|---|---|
| `SEC-01` | default key in `auth.py` | 1: the API does not start without a usable key |
| `SEC-01` | no minimum key length | 1: the API does not start without a usable key |
| `SEC-02` | `tenant_id` as `str` in `User` | 5: malformed tenant (4 cases) and the token's positive control |
| `SEC-06` | `str(e)` to the client in `POST /chat/` | 1: internal failure in a normal answer |
| `SEC-06` | `str(e)` in the stream's error event | 1: internal failure during the stream |
| `SEC-06` | `str(e)` to the client in `POST /ingest/` | 1: internal failure in ingestion |
| `BUG-01` | store the stream object, with the progress | 1: what is stored carries no progress messages |
| `BUG-01` | evaluate the accumulated text instead of the clean one | 1: the evaluator gets the clean answer |
| `BUG-09` | do not append the supervisor's answer to the stream | 6: the three supervisor paths, plus no duplication |

### New finding at the end (2026-09-17)

The full suite ended with code 134 in ~7 of every 8 runs, **after** all 129 tests had passed. The macOS report points to the telemetry of `onnxruntime` (it comes with FlashRank): its events thread processes an HTTP response when the interpreter is already shutting down and aborts the process. It only happened in the full suite, the only one that loads FlashRank by importing the application. Mitigated in `tests/conftest.py` with `onnxruntime.disable_telemetry_events()` before anything imports the re-ranker: 20 runs in a row without failure. It is catalogued as a separate finding in the audit, with the decision about production left to the user.

## 7. Wrap-up

- [x] 7.1 Run the full `uv run pytest` twice in a row; verify that they pass, measure the total time and check that no test containers or volumes remain
- [x] 7.2 Verify that the API layer passes on its own and without Docker (`uv run pytest tests/api` with `docker` off the PATH) and that `uv run pytest tests/unit` stays around 0.3 s
- [x] 7.3 Check that the development database is left intact: counts 22/128/4/3/0 and the same volume before and after
- [x] 7.4 Note in `docs/TECHNICAL_AUDIT.md` that `SEC-01`, `SEC-02`, `SEC-06`, `BUG-01` and `BUG-09` now have automatic regression tests, with the negative control table
- [x] 7.5 Commits on the `test/api-regression-layer` branch, one per unit of work and with the measurements in the body; verify with `git status` that nothing is left uncommitted outside what was decided
