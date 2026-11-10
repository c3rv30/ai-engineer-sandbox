## Why

The generator sometimes answers an English question in Spanish when the retrieved context is long and in Spanish. The current rule asks it to "write in the same language as the Question", so the model has to work out the language itself, and a long Spanish context pulls it the other way. It was seen with the code from before the English translation (8 English answers out of 9) and not with the current code (9 of 9). That is too few samples to say whether moving the rule to the end of the prompt (`fef8f31`) helped. Nothing in the system measures or records the mismatch, so a wrong-language answer is also cached and served again to every similar question.

## What Changes

- **The supervisor decides the answer language.** `QueryIntent` (`src/services/router.py`) gets a required `answer_language` field (`es` or `en`). The supervisor already reads the question to route it, and it writes it into `AgentState` on every path. Its own `direct_answer` (greetings and out-of-scope topics) follows that field too.
- **The generator gets an order, not a rule to work out.** `src/services/extractor.py` receives `answer_language` and its prompt says "Write 'answer' in English" (or Spanish), still after the Context. The relative rule ("the same language as the Question") is removed. **BREAKING (internal):** `generate_answer` and `generate_answer_stream` take a new required `answer_language` argument, and `tests/evals/test_rag.py` is updated to pass it.
- **Deterministic language detection.** A new pure module, `src/services/language.py`, built on `lingua-language-detector` and limited to Spanish and English. It returns no language when it cannot tell, for example on a short greeting. It builds both the generator's instruction and the check of the final answer.
- **A safety net that never blocks.** After the graph ends, both chat endpoints compare the language of the answer with the supervisor's decision. On a mismatch they log a warning and skip the semantic cache, but they still return the answer, because in streaming the text has already reached the client. The background evaluator stores the expected and detected language with its row in `rag_evaluations` (two nullable columns, with a migration for an existing database). Tool answers are not checked, because their text is a fixed template.
- **A language eval with enough samples.** A runner in `tests/evals/` asks a fixed set of questions through the real graph: about 10 per language, including follow-ups whose history is in the other language, repeated to reach about 100 answers per variant. Collecting the answers and scoring them are separate steps, so the same scorer can score answers collected with the code from before the change. The metric is the share of answers written in the question's language, per language and with a 95% confidence interval. When the run has the supervisor's decision, the eval also reports how accurate that decision is.
- **Regression tests and documentation.** Unit tests for the detector, the instruction and the cache policy. API tests for the safety net (a mismatch is logged and not cached, and the evaluator receives both languages). A new audit finding (`BUG-11`) with the before/after measurement. The README sentence on corpus language vs. question language is updated.

## Capabilities

### New Capabilities
- `answer-language`: who decides the language of an answer, how the generator and the supervisor's direct answers follow that decision, and how a mismatch is detected and recorded without blocking the answer.
- `answer-language-eval`: how the share of answers in the question's language is measured, on which question set and with how many samples, and how two code versions are compared.

### Modified Capabilities
- `regression-test-suite`: the cache policy requirement gains a scenario, so an answer whose language does not match the decided one is not cacheable. A new requirement covers the answer language regression (detector, instruction and safety net).

## Impact

- **Production code:** `src/services/router.py`, `src/services/extractor.py`, `src/services/agent_graph/state.py`, `src/services/agent_graph/nodes.py`, `src/services/cache_policy.py`, `src/services/evaluator.py`, `src/api/routers/chat.py`, and the new `src/services/language.py`.
- **Database:** two nullable columns in `rag_evaluations` (`sql/01_init.sql` and `sql/migrations/apply_answer_language.sql`). Existing rows stay valid.
- **Dependencies:** `lingua-language-detector` (2.2.0 ships `cp314` wheels) as a runtime dependency.
- **Cost of measuring:** about 200-300 LLM calls per variant, so roughly 500 for before plus after. Measuring needs a working `ANTHROPIC_API_KEY` (the one in `.env` returned 401 on 2026-11-09) and the development database restored from `~/Backups/ai_engineer_sandbox/`, which no longer exists. Both are confirmed with the user before running anything.
- **Documentation:** `README.md` and `docs/TECHNICAL_AUDIT.md`.
- **Out of scope:** multilingual embeddings (`paraphrase-multilingual-MiniLM-L12-v2`, which needs a re-ingestion) as a separate change; languages other than Spanish and English; the fixed English progress messages and tool templates; and cross-language hits of the semantic cache, which is checked before the supervisor runs.
