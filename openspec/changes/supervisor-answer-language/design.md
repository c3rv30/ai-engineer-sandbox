## Context

See `proposal.md` (Why) and the three spec deltas for the requirements. What shapes the design, read from the current code:

- **The supervisor already returns a structured object.** `analyze_query` (`src/services/router.py`) asks Haiku for a `QueryIntent` through Instructor. A field with a closed type that fails validation is retried by Instructor with the error sent back, the same mechanism `RAGEvaluation` relies on since `DOC-02`. Its prompt already has a `LANGUAGE:` paragraph: `direct_answer` goes in the user's language, and the search queries and HyDE go in Spanish.
- **The generator's prompt has one builder.** `_build_prompt` in `src/services/extractor.py` is shared by `generate_answer` and `generate_answer_stream`, and its language rule is relative ("the same language as the Question above"). It comes after the Context since `fef8f31`.
- **`AgentState` is a `TypedDict` and only nodes write it.** `supervisor_node` returns a partial update on each of its three branches (direct answer, tool, knowledge search). `generator_node` reads `query`, `documents`, `user_profile` and `history`. The reviewer can run the generator a second time.
- **The endpoints are the only place that sees both the final answer and the cache decision.** `chat.py` calls `is_cacheable(intent_type, answer_dict)` and schedules `evaluate_rag_response(tenant_id, query, answer, documents)`. The stream endpoint already pulls `intent_type` and `documents` out of the `updates` channel, and it keeps a clean `final_dict` apart from the `stream_dict` the client sees (`BUG-01`). `chat.py` has had a `logger` since `SEC-06`.
- **`rag_evaluations` is written only by the evaluator**, through `tenant_connection`. `app_user` has `GRANT ALL` on the table, which covers new columns. New columns need `sql/01_init.sql` for new databases and a migration in `sql/migrations/` for existing ones.
- **The pure logic layer is guarded.** `tests/unit/test_layer_purity.py` imports a list of modules in a subprocess and fails if `anthropic`, `langgraph`, `sentence_transformers` or `flashrank` show up. `extractor.py` creates an Anthropic client on import, so it cannot be imported there. The API layer (`tests/api/`) already imports it, with doubles for the graph and the services.
- **`tests/conftest.py` pins `DATABASE_URL` to the disposable database on port 5439.** Anything collected by pytest connects there, which has no corpus. That is also why `tests/evals/test_rag.py` cannot retrieve anything today.
- **The measurement environment does not exist right now.** The development database was lost on 2026-11-07, and the `ANTHROPIC_API_KEY` in `.env` returned 401 on 2026-11-09.

## Goals / Non-Goals

**Goals:**
- One explicit decision, made once per query and carried by the state, that every writer of answer text follows.
- A detector that gives the same result on every run and every machine, used both by the application and by the eval, so the eval measures exactly the signal production records.
- A measurement that can tell "better" from "same" honestly, and that can be run on the code from before this change without porting anything to it.

**Non-Goals:**
- Rewriting a wrong-language answer, or retrying it. The client already has the text (see the `answer-language` spec).
- Detecting the question's language before the supervisor runs. That would be needed to fix cross-language cache hits, which are out of scope.
- Making the eval a pass/fail gate in CI. It costs hundreds of calls and needs the corpus.

## Decisions

### D1. `answer_language: Literal["es", "en"]`, required, in `QueryIntent`
The field has no default. If the model leaves it out or writes `"English"`, Instructor retries with the validation error instead of the code falling back silently. The supervisor prompt's `LANGUAGE:` paragraph says how to decide: the language of the latest user message; an explicit request for a language wins; the history does not count; any other language maps to `en`. It also says `direct_answer` is written in `answer_language`. The search queries and HyDE stay in Spanish.
- *Rejected alternative: detecting the question's language with lingua instead of asking the supervisor.* Questions are short, often mix in English technology names ("¿Qué hizo con Kubernetes y Terraform?"), and can ask for a language explicitly. The supervisor reads the question anyway, and costs a few output tokens more, not a call.
- *Rejected alternative: a free `str` with a description, like `intent_type`.* `cache_policy.py` already has to treat `intent_type` as untrusted free text. A closed type moves that check to validation.

### D2. The decision travels in `AgentState`
`AgentState` gets `answer_language: str`. `supervisor_node` writes it on all three branches, including the direct-answer and tool branches, which end the graph, so that the endpoints can read it whatever the path. `generator_node` reads `state["answer_language"]` and passes it on, so the reviewer's second run uses the same value without asking again. `chat.py` initializes it to `""` in both `initial_state` blocks, like `intent_type`.

### D3. The generator gets an order; the relative rule is removed
`generate_answer` and `generate_answer_stream` take a required `answer_language` argument, and `_build_prompt` puts the instruction built by `language.answer_instruction(code)` where the relative rule is now: after the Context. For example: "LANGUAGE: Write 'answer' in English, even though the Context is in Spanish. Translate what you take from the Context; keep proper nouns, company names and technology names as they are."
- *Rejected alternative: keeping the relative rule as a fallback when no language is given.* It would leave two code paths, and the only caller without a decision is `tests/evals/test_rag.py`, which is updated to pass `"en"` for its English question.
- *Rejected alternative: moving `_build_prompt` to a pure module so tests/unit can check it.* It would be a refactor this change does not need. The instruction text lives in the pure module and is unit-tested there. The prompt as a whole is checked in the API layer, which already imports `extractor.py`.

### D4. Detector: `lingua-language-detector`, Spanish and English only, in `src/services/language.py`
`detect_language(text) -> "es" | "en" | None` builds a lingua detector for exactly two languages, with a minimum relative distance so that it returns `None` when the two are too close. It builds the detector once, lazily (`functools.cache`). Before detecting, it removes fenced and inline code, which is neither language, and returns `None` below a minimum number of letters. The module also exposes the supported codes, `answer_instruction(code)`, and `check_answer_language(expected, answer) -> LanguageCheck(expected, detected, mismatch)`, where `mismatch` holds only when both values are known and differ. It imports no LLM client and no embedding model, and it is added to `PURE_MODULES`.
- *Why lingua:* it is deterministic, works offline with no model download, is accurate on short and mixed text, and 2.2.0 ships `cp314` wheels.
- *Rejected alternatives:* an LLM judge (not deterministic, and it costs a call per answer); `langdetect` (random unless seeded, weak on short text); fastText `lid.176` (a 126 MB model file to download and manage).
- The distance threshold and the minimum length are set from the eval's collected answers (task 6.4), not guessed.
- *Changed in task 6.4: detection by segments.* Judging the whole text at once took 3 of the 200 collected answers, all in English, for Spanish with full confidence (they keep the Spanish names of degrees, as the generator's order asks), and no threshold could fix it, because the confidences come out at 0 or 1. The detector now splits the text into segments (`detect_multiple_languages_of`) and the language covering most letters wins, if it covers at least `MIN_SHARE` (0.6) of them; otherwise the answer is undetermined. In the 200 answers the right language never covered less than 62%. It costs ~4.6 ms per answer instead of ~0.6 ms, after the answer has been sent.

### D5. The check runs in the endpoints, after the graph, before the cache decision
In both endpoints, once the final answer exists and `intent_type` is not `tool_execution`, `chat.py` calls `check_answer_language(answer_language, answer_text)` on the clean answer text: `final_dict["answer"]` in streaming, never the accumulated text with progress lines. Detection takes milliseconds and happens after the last event is sent, so the client sees no change. The result does three things: on a mismatch, `logger.warning` with expected, detected and intent; `is_cacheable(..., language_mismatch=check.mismatch)`; and both languages are passed to `evaluate_rag_response`.
- *Rejected alternative: inside `generator_node`.* It would miss the supervisor's direct answers, and the cache decision is made in the endpoints anyway.
- *Rejected alternative: inside the evaluator only.* It runs only for answers with documents, in the background, after the cache has already been written, and it loses its row when the judge fails.

### D6. `is_cacheable` gains a keyword, it does not detect
`is_cacheable(intent_type, answer, *, language_mismatch=False)`. The policy stays a pure decision over values it is given, as it is today, and its existing callers and tests keep working unchanged. Detection stays in one place (D5).

### D7. Two nullable columns in `rag_evaluations`
`expected_language TEXT` and `detected_language TEXT`, each with `CHECK (... IN ('es', 'en'))`, nullable: `NULL` for rows stored before this change and for an undetermined detection. They go in `sql/01_init.sql` and in an idempotent `sql/migrations/apply_answer_language.sql` (`ADD COLUMN IF NOT EXISTS`). `evaluate_rag_response` gets two optional keyword arguments and inserts them. The mismatch rate in production can then be read with one query, next to the scores of the same answers.
- *Rejected alternative: a table of its own for language events.* It would need RLS, a `FORCE`, a policy and a `GRANT` (`HYG-07`). Its only gain is recording mismatches on direct answers, which the log already does.
- *Rejected alternative: a Langfuse score.* Langfuse is optional in this project, and its data cannot be queried next to `rag_evaluations`.

### D8. The eval is a runner in `tests/evals/answer_language/`, not a pytest test
- `questions.json`: the labeled set (D9).
- `collect.py --code-root PATH --tenant UUID --repeats N --out answers.jsonl`: puts `--code-root` first on `sys.path`, loads the **main repository's** `.env` before importing anything from `src` (the trap from `verificacion-e2e`), builds the graph with `build_graph()` and calls `ainvoke` with a state like the one in `chat.py`, with bounded concurrency. It writes one JSON line per answer: question id, expected language, repetition, answer text, `answer_language` from the final state (or `null`), `intent_type`, number of documents, error, and the `git rev-parse HEAD` of `--code-root`. Going through the graph and not the HTTP API skips the semantic cache, memory extraction and the evaluator, so the run reads the database but writes nothing to it.
- `score.py answers.jsonl [--baseline before.jsonl]`: detects with `src.services.language` from the main repository, computes the counts and a Wilson 95% interval per language, the supervisor's accuracy when `answer_language` is present, and, with `--baseline`, the comparison rule from the spec. It prints a Markdown report that can go in a commit body or the audit.
- None of the files is named `test_*.py`, and the runner never imports `tests/conftest.py`, so neither `uv run pytest` nor `--run-evals` collects it, and it is not pinned to port 5439.
- *Rejected alternative: a `pytest` test with a threshold.* `tests/conftest.py` would point it at the database without a corpus. A threshold on about 50 samples per language would also be a coin toss presented as a gate.
- *Rejected alternative: a single script that collects and scores.* The "before" code has no `language.py`, and scoring again after tuning the detector would cost another few hundred calls.

### D9. The question set
There are 10 questions per language: 8 matched pairs (the same question in Spanish and in English) and 2 follow-ups per language whose `history` is in the other language. They are written against the CV corpus and lean toward broad questions that pull a long Spanish context ("Summarize his cloud experience across all his jobs"), which is where the defect showed up. With `--repeats 5` that is 100 answers per variant, at the default `top_k` (15/10), which is what users get. `collect.py` accepts `--top-k-rerank` for a stress run, but the before/after comparison uses the defaults.

### D10. The "before" variant is the branch point, run from a worktree
`git worktree add --detach <scratchpad>/wt_before <branch point>` (today `develop` at `5284019`), using the main repository's `.venv` and `.env`. `collect.py` is run from the main repository with `--code-root` pointing at the worktree. Only the code under test changes; the runner, the question set and the scorer are the same. The worktree is removed at the end.

## Risks / Trade-offs

- **[The detector flags a Spanish answer full of English technology names as English, or the other way round]** → This causes a false mismatch: a spurious warning and an answer that is not cached. The answer itself is not affected. Mitigation: code is removed before detection, the distance threshold leans toward "undetermined", and the threshold is calibrated on the ~200 collected answers. Every mismatch the eval flags is reviewed by hand before the numbers are reported.
- **[The supervisor decides wrong, and the generator now obeys it]** → The relative rule could still get such a case right. Mitigation: the eval reports the decision's accuracy separately (spec, "Supervisor decision accuracy"), and the set includes follow-ups with history in the other language, which is the most likely way to fool it.
- **[The baseline barely fails (9 of 9 last time), so the eval may show no difference]** → That is a valid result, and the comparison rule says so rather than claiming an improvement. The change still adds the explicit decision, the recorded signal and the cache guard, and the report states which of these the numbers support.
- **[lingua adds memory and first-call latency to the API process]** → It is measured with `vmmap --summary` (physical footprint) and by timing the first detection, sequentially and with a warm disk cache (see `verificacion-e2e`). If the first call is slow, the detector is built in the app's `lifespan`. The decision is recorded in the commit.
- **[The graph double in `tests/api/doubles.py` drifts from the real update shape]** → The supervisor update now carries `answer_language`. The double is updated from `nodes.py` in the same commit as the node, and the end-to-end run of the eval exercises the real shape.
- **[Measuring costs ~500 calls and needs an environment that does not exist today]** → The database restore and the API key are confirmed with the user before any call, and the commit records the call count.

## Migration Plan

1. Merge the code. Until the migration runs, the evaluator's INSERT would fail on the new columns. It fails inside its own `try`, so it loses the evaluation row, as it does on any judge error, and never touches the answer. That is why the migration runs before the API is started on the new code.
2. Run `sql/migrations/apply_answer_language.sql` on the development database after restoring it. New databases get the columns from `sql/01_init.sql`.
3. Rollback: revert the code. The nullable columns can stay; the old INSERT names its columns and ignores them. Dropping them is optional and loses only the language data.

## Open Questions

- The exact minimum relative distance and minimum length for the detector. They come out of calibration (task 6.4) and do not change the specs.
- Whether the detector has to be warmed up in the `lifespan`. That depends on the measured first-call latency (Risks).
