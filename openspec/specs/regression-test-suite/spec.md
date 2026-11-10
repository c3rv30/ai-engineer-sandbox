## Purpose

Automatic regression net that keeps the defects fixed in the technical audit from coming back. It separates the logic that can be checked without infrastructure from multi-tenant isolation, which can only be demonstrated against a real Postgres.

## Requirements

### Requirement: Pure logic layer runs without infrastructure
The pure logic layer MUST run without a database, without LLM calls, without a `.env` file and without loading the embedding or re-ranking models. It MUST be possible to run it alone, without the database layer.

#### Scenario: Clone without configuration
- **WHEN** only the pure logic layer is run in a clone of the repository without `.env` and without Docker
- **THEN** all its tests are collected and run, and none fails because of missing configuration, a refused connection or an import

#### Scenario: No model loading
- **WHEN** only the pure logic layer is run
- **THEN** neither the embedding model nor the re-ranking model is loaded, and the whole run takes seconds, not the time it takes to import the API

### Requirement: Disposable database for the database layer
The database layer MUST run against a PostgreSQL database created for the run from an empty volume, with the repository's init scripts, and MUST delete it at the end, volume included. It MUST NOT connect to the development database or modify it, or touch its data volume.

#### Scenario: Freshly created database
- **WHEN** the database layer is run
- **THEN** the tests run against a database initialized in that same run, with the schema, policies and roles from the repository's scripts

#### Scenario: Cleanup at the end
- **WHEN** the run ends, with tests passed or failed
- **THEN** neither the container nor the volume of the test database remains

#### Scenario: The development database is not touched
- **WHEN** the full suite is run with the development database running
- **THEN** the counts of the development database and its volume are identical before and after

### Requirement: Explicit failure without Docker
If the database layer is selected and the disposable database cannot be started, the run MUST fail with a message stating the cause. It MUST NOT skip that layer's tests or count them as passed.

#### Scenario: Docker not available
- **WHEN** the full suite is run without Docker available
- **THEN** the run ends in failure and the message says the test database could not be started

#### Scenario: Explicit selection of the pure layer
- **WHEN** only the pure logic layer is run without Docker available
- **THEN** the run ends successfully, because the database layer was not selected

### Requirement: Collection scope
The default run MUST collect tests only from the project's tests directory, and MUST exclude the quality evaluations with an LLM judge.

#### Scenario: Loose scripts in the root
- **WHEN** the default suite is run
- **THEN** no `test_*.py` script in the repository root is collected or imported

#### Scenario: Quality evaluations excluded
- **WHEN** the default suite is run
- **THEN** the existing quality evaluation does not run, and only runs when explicitly selected

### Requirement: Every regression test proves it catches its defect
Every test tied to an audit finding MUST fail when the defect it protects against is reintroduced. That check MUST be done before the test is accepted.

#### Scenario: Negative control
- **WHEN** the behavior from before a finding's fix is reintroduced into the code
- **THEN** at least one test tied to that finding fails

### Requirement: Cache policy regression
The suite MUST verify that the semantic cache is only read or written when the answer is reusable for any similar request (`BUG-02`, `BUG-06`, `BUG-10`, `BUG-11`).

#### Scenario: Non-cacheable intent
- **WHEN** the intent of the answer is a tool, an out-of-scope topic or an unrecognized value
- **THEN** the answer is not cacheable

#### Scenario: Insufficient answer
- **WHEN** the answer says it needs more information, or its confidence is below 0.5 or missing
- **THEN** the answer is not cacheable

#### Scenario: Reusable answer
- **WHEN** the intent is a knowledge search or a greeting, it needs no more information and its confidence is at least 0.5
- **THEN** the answer is cacheable

#### Scenario: Answer in the wrong language
- **WHEN** an otherwise cacheable answer is detected in a language other than the decided one
- **THEN** the answer is not cacheable

#### Scenario: Custom retrieval parameters
- **WHEN** a request carries `top_k_retrieve` or `top_k_rerank` other than 15 and 10
- **THEN** the request may neither read nor write the cache

#### Scenario: Request with history
- **WHEN** a request with the default parameters carries conversation history
- **THEN** the request may neither read nor write the cache

#### Scenario: Out-of-range parameters
- **WHEN** a request carries `top_k_retrieve` outside 1-50 or `top_k_rerank` outside 1-20
- **THEN** the request is rejected by validation

### Requirement: Self-correction loop regression
The suite MUST verify that each retry widens the search within the maximums, and that there is no retry when widening it cannot change the context (`BUG-05`).

#### Scenario: Widening per retry
- **WHEN** the retrieval window is computed with base 15/10 on the first pass and the next two retries
- **THEN** the window is 15/10, 30/15 and 45/20

#### Scenario: Cap at the maximums
- **WHEN** the widening would exceed the API maximums
- **THEN** the window stays at 50 candidates and 20 documents

#### Scenario: Saturated window
- **WHEN** the next retry's window would be the same as the current one
- **THEN** retrieval is considered exhausted

#### Scenario: Exhausted corpus
- **WHEN** no search filled its candidate quota and the generator already received all the unique candidates
- **THEN** retrieval is considered exhausted

#### Scenario: Reviewer decision
- **WHEN** the generator asks for more information
- **THEN** the search runs again only if retrieval is not exhausted and two passes have not been made yet; otherwise, it ends

### Requirement: Conversation history regression
The suite MUST verify that the history the client sends becomes context for the prompt in a bounded way that is robust to malformed turns (`BUG-03`).

#### Scenario: Turn window
- **WHEN** the history has more than four turns
- **THEN** only the last four are included, in order

#### Scenario: Malformed turns
- **WHEN** the history contains turns that are not objects or that have no role or content
- **THEN** those turns are dropped without error and the rest are included

#### Scenario: Empty or unusable history
- **WHEN** the history is empty or none of its turns is usable
- **THEN** the result is an empty string, with no header

### Requirement: Ingestion file name regression
The suite MUST verify that the file name the client sends is reduced to a name without path components before being used as the document's origin (`SEC-04`).

#### Scenario: Directory traversal
- **WHEN** the name sent contains path components with `/` or `\`, including `..`
- **THEN** the recorded origin is only the last component

### Requirement: Tenant signature regression
The suite MUST verify that the signature the application computes matches the one the database verifies for the same tenant and the same key (`SEC-05`).

#### Scenario: Matching signature
- **WHEN** the application signs a tenant with a key, and the database computes the HMAC-SHA256 of the same tenant with that key
- **THEN** the two signatures are identical

### Requirement: Evaluator score bounds regression
The suite MUST verify that a score outside the 0-1 range is rejected when validating the judge's answer, before it reaches the database (`DOC-02`).

#### Scenario: Out-of-range score
- **WHEN** any of the three scores is below 0 or above 1
- **THEN** validation fails

### Requirement: Tenant isolation regression
The suite MUST verify, against the disposable database and with the application role, that a tenant only sees its rows when the context is signed with the right key (`SEC-05`, `SEC-03`, `PERF-01`). Every isolation check MUST come with a positive control from the tenant that owns the data.

#### Scenario: Valid signed context
- **WHEN** the application role queries with a tenant's context signed with the right key
- **THEN** it sees that tenant's rows and none from another

#### Scenario: Unsigned context or fake signature
- **WHEN** the application role sets a tenant without a signature, or with a signature that does not match the key
- **THEN** it sees no rows

#### Scenario: Tenant rewritten from the statement itself
- **WHEN** a query with a tenant's signed context rewrites the tenant from the statement itself
- **THEN** it gets no rows from the other tenant

#### Scenario: Injection in the GraphRAG query
- **WHEN** the knowledge graph search receives the `SEC-03` injection payload as the question
- **THEN** it returns no relations from another tenant

#### Scenario: Question words as data, not as SQL
- **WHEN** the graph search receives, with a tokenizer that lets quotes through, a tautology or a word with an apostrophe
- **THEN** it returns no relations that match no word, and does not fail with an SQL syntax error

#### Scenario: Connection reused from the pool
- **WHEN** a connection used with a tenant's context goes back to the pool and another operation reuses it without setting a context
- **THEN** that operation sees no rows from the previous tenant

#### Scenario: Transaction-local context
- **WHEN** the transaction in which the application set a tenant's context ends, even if the connection is not reset when it goes back to the pool
- **THEN** the connection no longer keeps the tenant or its signature

### Requirement: Application role privileges regression
The suite MUST verify, against the disposable database, that the application role has no more privileges than it needs (`HYG-07`, `SEC-07`).

#### Scenario: New table in the public schema
- **WHEN** the superuser creates a new table in the public schema
- **THEN** the application role cannot read it

#### Scenario: Schema creation
- **WHEN** the application role tries to create a schema
- **THEN** the operation is denied for lack of privileges

#### Scenario: The role's own settings
- **WHEN** the default settings stored for the application role are inspected
- **THEN** there are none

#### Scenario: Unreachable signing key
- **WHEN** the application role tries to read the signing key
- **THEN** the operation is denied

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

### Requirement: Answer language regression
The suite MUST verify that the generator gets an explicit instruction naming the decided language, and that the language detector tells Spanish from English and admits when it cannot tell. It MUST also verify that a mismatch is logged and recorded without changing the answer (`BUG-11`).

#### Scenario: Explicit instruction
- **WHEN** the generator's prompt is built for a question whose decided language is English
- **THEN** the prompt orders the answer in English and does not ask the model to match the question's language

#### Scenario: Detector on clear text
- **WHEN** the detector gets a paragraph of Spanish or of English that mixes in technology and company names
- **THEN** it returns that language

#### Scenario: Detector on too little text
- **WHEN** the detector gets a one-word greeting or an empty string
- **THEN** it returns undetermined

#### Scenario: Safety net at the endpoints
- **WHEN** the graph double returns an English decision and a Spanish answer, on `/chat/` and on `/chat/stream/`
- **THEN** the client gets the same answer, the log gets the mismatch warning, the cache double is not asked to store it, and the evaluator double gets both languages

#### Scenario: Matching answer at the endpoints
- **WHEN** the graph double returns an English decision and an English answer
- **THEN** no warning is logged and the answer is stored in the cache as before
