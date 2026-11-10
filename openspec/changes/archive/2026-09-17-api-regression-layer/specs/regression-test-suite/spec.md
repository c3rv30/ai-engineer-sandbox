## ADDED Requirements

### Requirement: API layer runs with doubles
The API layer MUST exercise the full HTTP application without connecting to PostgreSQL and without calling any LLM, replacing the agent graph and the data services with doubles that record what they were called with. It MUST NOT require Docker, and MUST be possible to run alone.

#### Scenario: No infrastructure
- **WHEN** only the API layer is run without Docker and without the database running
- **THEN** all its tests pass, and none opens a connection to PostgreSQL or calls an LLM

#### Scenario: Authentication is not doubled
- **WHEN** a test in this layer sends an authenticated request
- **THEN** the token is validated with the real authentication code, not with a double

### Requirement: Edge authentication regression
The suite MUST verify that the API rejects with 401 any token that cannot be validated, and that it does not start without a usable signing key (`SEC-01`, `SEC-02`).

#### Scenario: Token signed with another key
- **WHEN** a well-formed token signed with a key other than the server's is sent
- **THEN** the response is 401 and the graph does not run

#### Scenario: Token without user or tenant
- **WHEN** the valid token carries no user or no tenant
- **THEN** the response is 401

#### Scenario: Malformed tenant in the token
- **WHEN** the token carries a `tenant_id` that is not a UUID, for example a string with quotes or an SQL fragment
- **THEN** the response is 401, not an internal error, and the value does not reach the data layer

#### Scenario: Request without token
- **WHEN** a protected endpoint is called without an authorization header
- **THEN** the response is 401

#### Scenario: Missing or too short signing key
- **WHEN** the API is loaded without a JWT signing key, or with one shorter than 32 characters
- **THEN** startup fails with an error explaining the cause, instead of using a default value

### Requirement: Internal error detail regression
The suite MUST verify that, on an internal failure, the client gets a generic message with an identifier, and that the detail stays only in the log (`SEC-06`). Messages written for the client MUST be kept.

#### Scenario: Internal failure in a normal answer
- **WHEN** the graph raises an exception whose text contains a server path or a message from the LLM provider
- **THEN** the client gets a generic error with an identifier, that text does not appear in the response, and the log contains the traceback with the same identifier

#### Scenario: Internal failure during the stream
- **WHEN** the graph raises an exception while the stream is being emitted
- **THEN** the delivered event carries a generic error with an identifier, and the exception text does not appear

#### Scenario: Internal failure in ingestion
- **WHEN** the ingestion of an allowed file fails with an exception that names the server's temporary path
- **THEN** the client gets a generic error with an identifier and that path does not appear in the response

#### Scenario: Messages written for the client
- **WHEN** the request is rejected for an expected cause, such as a disallowed file extension or the graph not returning a final answer
- **THEN** the client gets the specific message for that cause, not the generic one

### Requirement: Cached object regression
The suite MUST verify that what is sent to be stored in the cache is the clean structured answer, without the progress messages the stream adds for the interface (`BUG-01`).

#### Scenario: What is stored versus what is emitted
- **WHEN** a stream request that can use the cache ends with a cacheable answer
- **THEN** the object the cache service receives contains no progress message, while the text emitted to the client does carry them

#### Scenario: The evaluator gets the clean answer
- **WHEN** that same request schedules the evaluation of the answer
- **THEN** the text the evaluator receives contains no progress messages either

### Requirement: Stream answer regression on every path
The suite MUST verify that `/chat/stream/` delivers the final answer also when the supervisor resolves it, without going through the generator (`BUG-09`).

#### Scenario: Greeting, out-of-scope topic or tool
- **WHEN** the supervisor resolves the request by itself, as with a greeting, an out-of-scope topic or a tool call
- **THEN** the stream's last event contains the answer, and not just the progress lines

#### Scenario: Generator answer
- **WHEN** the request is resolved by the generator emitting its text token by token
- **THEN** the last event contains the full answer exactly once, without duplicating it
