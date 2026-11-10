## Purpose

Decides the language of every answer once, at the start, and makes the rest of the pipeline follow that decision. A wrong-language answer is detected and recorded, but it never blocks or delays the answer the client gets.

## ADDED Requirements

### Requirement: The supervisor decides the answer language
For every query, the supervisor MUST decide the language of the answer, either Spanish or English, as part of its routing decision. The decision MUST be available to every later step of the graph, whatever path the query takes.

#### Scenario: English question
- **WHEN** the user writes a question in English
- **THEN** the decided answer language is English

#### Scenario: Spanish question
- **WHEN** the user writes a question in Spanish
- **THEN** the decided answer language is Spanish

#### Scenario: History in the other language
- **WHEN** the previous turns of the conversation are in Spanish and the new question is in English
- **THEN** the decided answer language is English, because the language of the latest question is what counts

#### Scenario: Explicit request
- **WHEN** the user asks, in either language, to get the answer in a specific one of the two languages
- **THEN** the decided answer language is the one the user asked for

#### Scenario: Unsupported language
- **WHEN** the user writes in a language other than Spanish or English
- **THEN** the decided answer language is English

### Requirement: The generator writes in the decided language
The generator MUST receive the decided language as an explicit instruction naming that language. It MUST NOT be asked to infer the language from the question. Proper nouns, company names and technology names MUST be kept as they appear in the context.

#### Scenario: English question over a Spanish context
- **WHEN** the decided language is English and every retrieved document is in Spanish
- **THEN** the generator is told to write the answer in English, and the answer is in English

#### Scenario: Retry of the self-correction loop
- **WHEN** the reviewer sends the query back to the researcher and the generator runs a second time
- **THEN** the second run gets the same decided language as the first

### Requirement: Direct answers follow the decided language
When the supervisor answers by itself, for a greeting or an out-of-scope topic, its answer MUST be written in the decided language.

#### Scenario: Greeting in English
- **WHEN** the user writes "Hi, how are you?"
- **THEN** the supervisor's direct answer is in English

### Requirement: Search queries stay in the corpus language
The search query variations and the hypothetical document MUST be written in Spanish, the language of the corpus, whatever the decided answer language is.

#### Scenario: English knowledge question
- **WHEN** the user asks a knowledge question in English
- **THEN** the decided answer language is English and the search variations and the hypothetical document are in Spanish

### Requirement: Answer language is checked after the answer
After the graph produces a final answer, both chat endpoints MUST detect the answer's language with a deterministic detector limited to Spanish and English, and compare it with the decided language. If the detector cannot tell, the result MUST be "undetermined", which is not a mismatch.

#### Scenario: Matching answer
- **WHEN** the decided language is English and the answer is in English
- **THEN** no mismatch is recorded

#### Scenario: Mismatched answer
- **WHEN** the decided language is English and the answer is in Spanish
- **THEN** a mismatch is recorded with the expected and the detected language

#### Scenario: Too little text to tell
- **WHEN** the answer is too short or too ambiguous for the detector
- **THEN** the detected language is undetermined and no mismatch is recorded

#### Scenario: Tool answer
- **WHEN** the query was resolved by a tool
- **THEN** the answer's language is not checked, because its text is a fixed template

### Requirement: A mismatch never blocks the answer
A language mismatch MUST NOT change, delay, retry or reject the answer the client gets, on either endpoint.

#### Scenario: Mismatch while streaming
- **WHEN** a streamed answer turns out to be in the wrong language
- **THEN** the client gets exactly the same events it would get without the check

#### Scenario: Mismatch without streaming
- **WHEN** a non-streamed answer turns out to be in the wrong language
- **THEN** the endpoint returns that answer with status 200

### Requirement: A mismatch is recorded as a signal
Every mismatch MUST be written to the application log with the expected and the detected language. When the answer is evaluated in the background, the stored evaluation MUST carry the expected and the detected language, including when they match.

#### Scenario: Mismatch log line
- **WHEN** a mismatch is detected
- **THEN** the application log gets a warning with the expected language, the detected language and the intent

#### Scenario: Evaluated knowledge answer
- **WHEN** a knowledge answer with retrieved documents is evaluated in the background
- **THEN** the stored evaluation records the expected language and the detected one, which is empty when undetermined

#### Scenario: Evaluations stored before this change
- **WHEN** the evaluations table is read after the change is applied to an existing database
- **THEN** the rows stored before the change are still there, with both languages empty

### Requirement: A mismatched answer is not cached
An answer whose detected language does not match the decided language MUST NOT be stored in the semantic cache, even when it is otherwise cacheable.

#### Scenario: Cacheable answer in the wrong language
- **WHEN** a first knowledge question without history gets a confident answer in the wrong language
- **THEN** the answer is returned to the client but not stored in the cache

#### Scenario: Undetermined language
- **WHEN** an otherwise cacheable answer has an undetermined language
- **THEN** the language check does not prevent it from being cached
