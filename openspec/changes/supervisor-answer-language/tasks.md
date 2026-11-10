## 1. Language detector and instruction

- [x] 1.1 Add `lingua-language-detector==2.2.0` as a runtime dependency with `uv add`; verify that `uv run --no-sync python -c "import lingua"` works and that `uv run pytest -m "not db"` still collects the same number of tests as before
- [x] 1.2 Write `src/services/language.py` (D4): supported codes, `answer_instruction(code)`, `detect_language(text)` with code removal, minimum length and a lazily built two-language detector, and `check_answer_language(expected, answer)`; verify that `answer_instruction("xx")` raises and that importing the module does not build the detector
- [x] 1.3 Add `src.services.language` to `PURE_MODULES` in `tests/unit/test_layer_purity.py`; verify that the guard passes, and that it fails if `language.py` imports `src.services.router` on purpose
- [x] 1.4 Write `tests/unit/test_language.py`: Spanish and English paragraphs that mix in technology and company names, a one-word greeting, an empty string, a code-only answer, and `check_answer_language` for match, mismatch and undetermined; verify that it passes in `uv run pytest tests/unit` without `.env`, and time the first detection call

## 2. Supervisor decides the language (`BUG-11`)

- [x] 2.1 Add the required `answer_language: Literal["es", "en"]` field to `QueryIntent`, and rewrite the prompt's `LANGUAGE:` paragraph with the decision rules from D1 (latest message, explicit request, history does not count, other languages go to `en`); `direct_answer` follows `answer_language`, and the search queries and HyDE stay in Spanish. Verify with a test in `tests/api/` that `QueryIntent` rejects `"English"` and a missing value
- [x] 2.2 Add `answer_language` to `AgentState`, write it from `supervisor_node` on all three branches, and initialize it to `""` in both `initial_state` blocks in `chat.py`; verify with `uv run pytest tests/api` that the graph still builds
- [x] 2.3 Update `tests/api/doubles.py` so that the supervisor update carries `answer_language`, matching the shape `nodes.py` now emits; verify that the whole API layer passes

## 3. Generator gets an explicit order (`BUG-11`)

- [x] 3.1 Add the required `answer_language` argument to `generate_answer` and `generate_answer_stream`, put `answer_instruction(answer_language)` after the Context in `_build_prompt`, remove the relative rule, and pass `state["answer_language"]` from `generator_node`; verify that `grep -n "same language as the Question" src/` finds nothing
- [x] 3.2 Write a test in `tests/api/test_answer_language.py` (spec scenario "Explicit instruction"): for `answer_language="en"`, the prompt orders English after the Context and does not ask to match the question's language. Run the negative control: put the relative rule back, check that the test fails, and restore it
- [x] 3.3 Update `tests/evals/test_rag.py` to pass `answer_language="en"`; verify that `uv run pytest --run-evals --collect-only` collects it without errors

## 4. Non-blocking safety net (`BUG-11`)

- [x] 4.1 Add the `language_mismatch` keyword to `is_cacheable` (D6) and the "Answer in the wrong language" scenario to `tests/unit/test_cache_policy.py`; verify that the existing cache tests pass unchanged, and run the negative control by ignoring the keyword
- [x] 4.2 Add the nullable `expected_language` and `detected_language` columns with their `CHECK` to `rag_evaluations` in `sql/01_init.sql`, and write the idempotent `sql/migrations/apply_answer_language.sql`; verify with a test in `tests/db/` that `app_user` can insert both languages and `NULL`, and that `'pt'` is rejected
- [x] 4.3 Give `evaluate_rag_response` the two optional keyword arguments and insert them; verify that the database test from 4.2 passes with a row written by the evaluator's own SQL
- [x] 4.4 In both endpoints of `chat.py`, run `check_answer_language` on the clean answer when the intent is not `tool_execution`, then log the mismatch with `logger.warning`, pass `language_mismatch` to `is_cacheable`, and pass both languages to the evaluator (D5). In streaming, take `answer_language` from the supervisor's update and the text from `final_dict`, never from the accumulated text
- [x] 4.5 Write the API tests from the spec scenarios "Safety net at the endpoints" and "Matching answer at the endpoints", on `/chat/` and `/chat/stream/`: identical events and status for the client, one warning, no cache write on a mismatch, both languages received by the evaluator double, and no check for a tool answer. Run the negative control: remove the `language_mismatch` argument in `chat.py`, check that a test fails, and restore it
- [x] 4.6 Run the full suite with `uv run pytest`; verify that it passes, and note the test count and time in the commit

## 5. Language eval runner

- [x] 5.1 Write `tests/evals/answer_language/questions.json` (D9): 8 matched pairs and 2 follow-ups per language with history in the other language, each labeled with its expected language; verify with a unit test that the set has at least 10 questions per language and at least 2 cross-language follow-ups
- [x] 5.2 Write `tests/evals/answer_language/score.py`: counts per language, Wilson 95% interval, no rate when there is nothing to score, supervisor accuracy when present, a list of questions with mismatches, and the `--baseline` comparison rule. Verify with `tests/unit/test_language_eval_score.py` on synthetic JSONL, which covers overlapping intervals, a regression and a language with only errors
- [ ] 5.3 Write `tests/evals/answer_language/collect.py` (D8): `--code-root`, `--tenant`, `--repeats`, `--concurrency`, `--top-k-rerank` and `--out`; the main repository's `.env` is loaded before any `src` import; the runner prints which database it uses and refuses port 5439; each JSONL line records the `HEAD` of `--code-root`. Verify with `--repeats 1` on two questions once the environment from group 6 exists, and check that `uv run pytest --run-evals --collect-only` does not collect anything from that directory
- [ ] 5.4 Document how to run the eval, including the cost per run and the worktree step, in a short `tests/evals/answer_language/README.md`; verify that the documented commands run as written

## 6. Measurement (needs the user's confirmation before any call)

- [ ] 6.1 Ask the user to confirm the cost (~500 LLM calls in total) and to provide a working `ANTHROPIC_API_KEY`; do not start without both
- [ ] 6.2 Restore the development database from `~/Backups/ai_engineer_sandbox/`, as `verificacion-e2e` says (roles without `ON_ERROR_STOP`), apply `apply_answer_language.sql`, and record which tenant owns the CV documents; verify the 22/128/4/3/0 counts before the migration and take a snapshot of the counts before measuring
- [ ] 6.3 Collect the "before" variant from a worktree at the branch point (D10) and the "after" variant from the branch, each with `--repeats 5` and the default `top_k`; verify that each file has 100 lines and that the database counts are unchanged afterwards
- [ ] 6.4 Calibrate the detector's distance threshold and minimum length on the collected answers, reviewing by hand every answer it flags or leaves undetermined. If the values change, re-run 1.4 and rescore without new calls
- [ ] 6.5 Score both variants and compare them with `score.py --baseline`; keep the report and the call count for the commit body
- [ ] 6.6 Measure the API process's physical footprint (`vmmap --summary`) and the first-detection latency, with and without the change, sequentially and with a warm disk cache; decide whether to warm the detector in the `lifespan`, and record the decision in the commit
- [ ] 6.7 Run one end-to-end check against a real uvicorn: an English question over a Spanish context on `/chat/stream/` and on `/chat/` (with `top_k_rerank` other than 10, so the cache is not used). Verify that the answers are in English and that a new row in `rag_evaluations` carries both languages, then purge the rows the check added (memory and evaluations)

## 7. Documentation

- [ ] 7.1 Catalog `BUG-11` in `docs/TECHNICAL_AUDIT.md`: the defect, the 8/9 and 9/9 evidence, the before/after report from 6.5 and its status, plus a row in the remediation plan; verify that the measured numbers match the report
- [ ] 7.2 Update `README.md` (the note at the top and the "Corpus language vs. question language" paragraph) to say that the supervisor decides the answer language and that a mismatch is logged and not cached; verify that nothing in the README still describes the relative rule

## Workflow follow-up

- Commit each group on `feat/supervisor-answer-language`, with the measurements in the commit body, and ask the user how to integrate the branch into `develop` (merge or fast-forward).
- Archive the change once the user has reviewed it, and decide with the user whether to sync the new `answer-language` and `answer-language-eval` specs into `openspec/specs/`.
