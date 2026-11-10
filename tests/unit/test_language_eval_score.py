"""Scorer of the answer language eval (BUG-11), on synthetic answers.

It decides whether a change "improved" anything, so its counting and its comparison
rule are pinned here: undetermined answers and errors never count as successes, and an
improvement needs confidence intervals that do not overlap.
"""
import json

import pytest

from tests.evals.answer_language.score import LanguageScore, compare, main, score, wilson

SPANISH = "Bryan trabajó en Betterfly como ingeniero de backend, donde desarrolló un motor de autorización."
ENGLISH = "Bryan worked at Betterfly as a backend engineer, where he built a centralized authorization engine."


def record(qid, language, answer, *, decided=None, error=None):
    return {"id": qid, "language": language, "answer": answer, "answer_language": decided, "error": error}


def scored(matches, mismatches):
    s = LanguageScore()
    s.matches, s.mismatches = matches, mismatches
    return s


def test_wilson_interval():
    assert wilson(0, 0) is None
    low, high = wilson(50, 50)
    # At 100% the interval does not collapse to a point.
    assert low == pytest.approx(0.9287, abs=1e-4) and high == 1.0
    assert wilson(0, 10)[0] == 0.0


def test_counts_per_language():
    scores = score([
        record("q1-en", "en", ENGLISH, decided="en"),
        record("q1-en", "en", SPANISH, decided="en"),
        record("q2-en", "en", "OK", decided="es"),
        record("q3-en", "en", None, error="RateLimitError"),
        record("q1-es", "es", SPANISH),
    ])
    en, es = scores["en"], scores["es"]
    assert (en.answers, en.matches, en.mismatches, en.undetermined, en.errors) == (4, 1, 1, 1, 1)
    # Undetermined and errors stay out of the rate: 1 match out of 2 determined.
    assert en.rate == 0.5
    assert en.mismatched_questions == {"q1-en": 1}
    # 3 decisions recorded (the error has none), one of them wrong.
    assert (en.decisions, en.decision_errors) == (3, 1)
    assert es.rate == 1.0
    # Code from before the change: no decision, so no accuracy.
    assert es.decision_accuracy is None


def test_a_language_with_only_errors_or_undetermined_has_no_rate():
    s = score([record("q", "es", None, error="boom"), record("q", "es", "Hola")])["es"]
    assert s.rate is None and s.interval is None


def test_overlapping_intervals_are_no_evidence_of_improvement():
    # 50/50 against 48/50: higher, but the intervals overlap.
    assert compare(scored(50, 0), scored(48, 2)) == "no evidence of improvement"


def test_improvement_needs_separate_intervals():
    assert compare(scored(50, 0), scored(30, 20)) == "improvement"


def test_any_drop_is_a_regression():
    assert compare(scored(49, 1), scored(50, 0)) == "regression"


def test_without_determined_answers_there_is_no_verdict():
    assert compare(scored(0, 0), scored(50, 0)).startswith("not comparable")


def test_report_with_baseline(tmp_path, capsys):
    before, after = tmp_path / "before.jsonl", tmp_path / "after.jsonl"
    before.write_text("\n".join(json.dumps(r) for r in [record("q", "en", SPANISH), record("q", "es", SPANISH)]))
    after.write_text("\n".join(json.dumps(r) for r in [record("q", "en", ENGLISH, decided="en"),
                                                         record("q", "es", SPANISH, decided="es")]))
    assert main([str(after), "--baseline", str(before)]) == 0
    out = capsys.readouterr().out
    assert "### Comparison" in out and "Questions with mismatches: `q` ×1" in out
