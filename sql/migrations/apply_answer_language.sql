-- BUG-11: the evaluation stores the language the supervisor decided and the one
-- detected in the answer, so the mismatch rate can be read next to the scores of the
-- same answers. Both are nullable: rows stored before this migration keep NULL, and so
-- does an answer whose language the detector could not tell.
--
-- Idempotent. The table-level GRANT ALL that app_user already has covers new columns.
-- Run it before starting the API on the new code: until then, the evaluator's INSERT
-- fails inside its own try and the evaluation row is lost (the answer is not affected).
--
-- Run as superuser:
--   psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
--       -f sql/migrations/apply_answer_language.sql

ALTER TABLE rag_evaluations
    ADD COLUMN IF NOT EXISTS expected_language TEXT CHECK (expected_language IN ('es', 'en')),
    ADD COLUMN IF NOT EXISTS detected_language TEXT CHECK (detected_language IN ('es', 'en'));
