## Context

See `proposal.md` (Why) and the `regression-test-suite` spec for the requirements. What shapes the design, read from the current code:

- **Everything that has to be doubled is a module name in `src/api/routers/chat.py`**: `agent_graph` (a global created with `build_graph()` at import time), `check_semantic_cache`, `save_semantic_cache`, `retrieve_user_facts`, `extract_and_save_facts` and `evaluate_rag_response`. In `src/api/routers/ingest.py`, `ingest_file`. Replacing them from the test does not require touching production.
- **The stream consumes two channels**: `agent_graph.astream(state, stream_mode=["updates", "custom"])` yields `(mode, chunk)` tuples. With `custom`, `chunk` is `{"delta": str}`; with `updates`, `{node_name: state_update}`. The endpoint tells the `generator` node apart from the rest: it appends the supervisor's answer to the accumulated text, and not the generator's, because that one was already emitted token by token (`BUG-09`).
- **`BUG-01` is exactly the difference between two objects**: `final_dict` (clean, the one that is stored and the one that goes to the evaluator) and `stream_dict` (with the progress, the one the client sees).
- **Authentication needs no doubles**: `get_current_user` decodes with `SECRET_KEY`, read when `src/api/auth.py` is imported, and builds `User`, where `tenant_id: uuid.UUID` rejects a malformed value (`SEC-02`).
- **`tests/conftest.py` already sets a random `JWT_SECRET_KEY` per run** before importing `src`, so the tests can sign tokens with the same key as the server.
- **`TestClient` delivers the SSE events all at once**: it is good for counting events and asserting on their content, not for measuring latency.
- **The application's `lifespan` opens the pool at startup**, and catches the failure if Postgres is not there. `TestClient` only runs the `lifespan` when used as a context manager.
- `starlette.testclient` and `httpx` 0.28.1 are already installed; nothing new needs declaring.

## Goals / Non-Goals

**Goals:**
- Pin the HTTP edge contract for the five fixes, with no network, no database and no Docker.
- That each test asserts on what the client sees or on what the services receive, not on how the endpoint is written.
- Not touching production code.

**Non-Goals:**
- Replacing the end-to-end verification: with the graph doubled, these tests say nothing about the quality of the answers or about the real integration.
- Measuring latency or the incremental behavior of the stream (`DOC-01`), which needs a real uvicorn.
- Covering the full ingestion: only its HTTP edge is exercised here, for `SEC-06`.

## Decisions

### D1. Doubles installed with `monkeypatch` on the router module
A fixture replaces each name in `src.api.routers.chat` (and `ingest_file` in `src.api.routers.ingest`) with a double that records the calls and returns whatever the test configures. `monkeypatch` restores them at the end of each test.
- *Rejected alternative: `app.dependency_overrides`.* It only covers FastAPI dependencies, and neither the graph nor the services are.
- *Rejected alternative: injecting the graph as a dependency in production.* It would change the code to make it testable, and the proposal is not to touch it.

### D2. A single builder for graph scripts
The `ainvoke` and `astream` doubles are built in a single helper module (`tests/api/doubles.py`) from a declarative "script": which nodes emit, with what state update, and what text the generator emits on the `custom` channel. That way the shape of the graph's data is written once, and the tests describe the case, not the protocol.
- *Accepted risk, see below:* if the real graph changes the shape of what it emits, the double can go out of date without anything failing.

### D3. Tokens signed in the test with the process's real key
The tests generate tokens with `jwt.encode` and the `JWT_SECRET_KEY` from the environment `tests/conftest.py` sets. For `SEC-01`, a token signed with another key; for `SEC-02`, a non-UUID `tenant_id` (including an SQL fragment, which is the finding's payload).
- *Rejected alternative: using `/auth/token`.* It works as a positive control, but it does not allow building the invalid tokens these tests are about. One case through the real endpoint is used as well, so as not to rely only on made-up tokens.

### D4. Startup without a key is checked in a subprocess
`SEC-01` includes the process not starting without `JWT_SECRET_KEY` or with a short one. Since the key is read when `src/api/auth.py` is imported, it is checked by launching a subprocess that imports the module with the modified environment and expecting a failure with an explanatory message. It is the same pattern as layer 1's purity guard.

### D5. `TestClient` without a context manager
The client is created as `TestClient(app)` without `with`, so the `lifespan` does not run and the layer does not try to open the Postgres pool. A separate test explicitly checks that no connection is opened during the layer, watching `asyncpg.connect`.
- *Rejected alternative: using `with` and letting the pool fail.* It works because the error is caught, but it leaves the layer depending on that `try` staying there.

### D6. Assertions on the SSE events, never on timings
The stream is read with `client.post(...)` and the events are extracted from the `data: ` lines. The assertions are on the number of events, the last event and the presence or absence of texts. No latencies (see Context).

### D7. Background tasks
`TestClient` runs the `BackgroundTasks` before returning control, so the memory and evaluator doubles record their calls and the test can assert on what they received, which is how half of `BUG-01` is checked.

### D8. Location and selection
`tests/api/`, with the `api` marker set automatically by its `conftest.py`, like `db` in layer 2. It is part of the default run. The application is imported once per session (session fixture), because that import costs ~10 s.

## Risks / Trade-offs

- **[The graph double drifts from the real shape]** → It is the main risk: a change in what the nodes emit would leave the tests green on a protocol that no longer exists. It is limited by concentrating the shape in `tests/api/doubles.py` and deriving it from `nodes.py`, and it is offset by the manual end-to-end verification, which remains mandatory for every finding. It is not eliminated.
- **[The doubles tie the tests to internal names]** → If the graph stops being a global of `chat.py`, the fixture has to change, not each test: that is why the doubles are installed in a single place.
- **[Importing the application costs ~10 s]** → The full suite goes from ~8 s to ~18 s. For iterating there is still `uv run pytest tests/unit`.
- **[A test could open a connection by accident]** → The D5 test catches it, failing if anything calls `asyncpg.connect` during the layer.
- **[`SEC-06` depends on the log collecting the traceback]** → It is checked by capturing the log with the `caplog` fixture and requiring the client's identifier to appear exactly once, next to the text that must not leave it.

## Migration Plan

There is no deployment. Order: fixture with the doubles and the client → authentication (`SEC-01`, `SEC-02`) → internal errors (`SEC-06`) → stored object (`BUG-01`) → stream paths (`BUG-09`) → negative control per finding → status in the audit. Undoing means reverting the branch; there are no production changes to revert.

## Open Questions

- Whether a test checking that the `lifespan` opens the pool at startup is also worth having. It is startup behavior, not an audit regression, and it changes neither the spec nor the tasks.
