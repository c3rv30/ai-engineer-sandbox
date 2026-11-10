"""Regression of the answer language (BUG-11).

The supervisor decides the language with a closed field, and the generator gets an
order naming it instead of a rule to work out. These modules create LLM clients on
import, which is why the checks live in this layer and not in tests/unit/.
"""
import pytest
from pydantic import ValidationError

INTENT = {"intent_type": "knowledge_search"}


@pytest.fixture
def query_intent(app_module):
    from src.services.router import QueryIntent

    return QueryIntent


@pytest.mark.parametrize("language", ["es", "en"])
def test_supervisor_decision_accepts_the_two_languages(query_intent, language):
    assert query_intent(**INTENT, answer_language=language).answer_language == language


@pytest.mark.parametrize("language", ["English", "spanish", "pt", ""])
def test_supervisor_decision_rejects_free_text(query_intent, language):
    with pytest.raises(ValidationError):
        query_intent(**INTENT, answer_language=language)


def test_supervisor_decision_is_required(query_intent):
    # Without a default, Instructor sends the error back to the model and retries.
    with pytest.raises(ValidationError):
        query_intent(**INTENT)
