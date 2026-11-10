## Purpose

Measures how often the system answers in the language of the question, with enough samples to tell a real difference between two versions of the code from noise.

## ADDED Requirements

### Requirement: Fixed, labeled question set
The eval MUST use a versioned question set with at least 10 questions per language. Each question MUST carry the language its answer is expected in. The set MUST include questions whose retrieved context is long and in Spanish, and follow-ups whose history is in the other language.

#### Scenario: Set contents
- **WHEN** the question set is loaded
- **THEN** it has at least 10 Spanish and 10 English questions, each labeled with its expected language, and at least two of them carry a history in the other language

### Requirement: Answers come from the real graph
The eval MUST get its answers from the real agent graph, with the real supervisor and generator and retrieval over the corpus. It MUST NOT go through the semantic cache, and it MUST NOT write anything to the database.

#### Scenario: Repeated question
- **WHEN** the same question is asked several times in one run
- **THEN** every repetition runs the graph, and none is answered from the cache

#### Scenario: Database left as it was
- **WHEN** a run ends
- **THEN** the database's row counts are the same as before the run

### Requirement: Sample size per variant
A measurement MUST collect at least 100 answers per code variant, with questions repeated to reach that number. Each language MUST get the same number of answers.

#### Scenario: Default run
- **WHEN** the eval runs with its default settings
- **THEN** it collects at least 50 answers per language

### Requirement: Collecting and scoring are separate
Collecting answers and scoring them MUST be separate steps. The collected answers MUST be saved to a file. The scorer MUST be able to score answers collected with any version of the code, including one from before this change.

#### Scenario: Scoring the code from before the change
- **WHEN** answers are collected with the code from before this change and scored with the current scorer
- **THEN** the scorer produces the same metrics it produces for the current code, minus those that need the supervisor's decision

#### Scenario: Scoring again without new calls
- **WHEN** a saved answers file is scored again
- **THEN** no LLM call is made

### Requirement: Language metric
The scorer MUST report the share of answers written in the language of the question, per language and overall. It MUST use the same deterministic detector as the application, with a 95% confidence interval. Undetermined answers and errors MUST be counted separately, never as successes.

#### Scenario: Report contents
- **WHEN** a set of answers is scored
- **THEN** the report gives, per language, the number of answers, matches, mismatches, undetermined answers and errors, and the match rate with its 95% interval, and it lists the questions that had mismatches

#### Scenario: No answers to score
- **WHEN** every answer of a language is an error or undetermined
- **THEN** the report shows no rate for that language instead of a 0% or a 100%

### Requirement: Supervisor decision accuracy
When the collected answers carry the supervisor's decision, the scorer MUST also report how often that decision matches the question's expected language. That separates supervisor errors from generator errors.

#### Scenario: Wrong decision
- **WHEN** the supervisor decides Spanish for a question labeled English
- **THEN** the report counts it as a decision error, and the answer's language is scored as usual

### Requirement: Comparing two variants
The eval MUST compare two scored variants per language and say whether the change is supported. An improvement MAY be claimed only when the confidence intervals do not overlap.

#### Scenario: Overlapping intervals
- **WHEN** the "after" rate is higher than the "before" rate but the intervals overlap
- **THEN** the comparison says there is no evidence of improvement

#### Scenario: Regression in one language
- **WHEN** the "after" rate is lower than the "before" rate for either language
- **THEN** the comparison reports a regression for that language

### Requirement: Not part of the default suite
The language eval MUST NOT run in the default test run or in the `--run-evals` run. It MUST run only when invoked explicitly, because each measurement costs hundreds of LLM calls.

#### Scenario: Default suite
- **WHEN** `uv run pytest` or `uv run pytest --run-evals` is run
- **THEN** the language eval makes no LLM call
