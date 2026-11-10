## MODIFIED Requirements

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

## ADDED Requirements

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
