"""The question set of the answer language eval (BUG-11).

The eval can only tell a real difference from noise if the set is balanced and covers
the case most likely to fool the supervisor: a follow-up whose history is in the
other language.
"""
import json
from collections import Counter
from pathlib import Path

from src.services.language import SUPPORTED_LANGUAGES, detect_language

QUESTIONS = Path(__file__).resolve().parents[1] / "evals" / "answer_language" / "questions.json"


def load():
    return json.loads(QUESTIONS.read_text())["questions"]


def test_at_least_ten_questions_per_language():
    counts = Counter(q["language"] for q in load())
    assert set(counts) == set(SUPPORTED_LANGUAGES)
    assert all(n >= 10 for n in counts.values()), counts


def test_unique_ids():
    ids = [q["id"] for q in load()]
    assert len(ids) == len(set(ids))


def test_cross_language_follow_ups():
    # The history really is in the other language: the detector says so (as a whole,
    # since a short question on its own is below its minimum length).
    follow_ups = Counter()
    for q in load():
        if q["history"]:
            history = " ".join(turn["content"] for turn in q["history"])
            assert detect_language(history) not in (None, q["language"]), q["id"]
            follow_ups[q["language"]] += 1
    assert all(follow_ups[language] >= 2 for language in SUPPORTED_LANGUAGES), follow_ups
