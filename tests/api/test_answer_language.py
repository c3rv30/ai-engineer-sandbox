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


def build_prompt(language, query="What did he do at Itaú?"):
    from src.models.search import RerankedResult
    from src.services.extractor import _build_prompt

    context = [RerankedResult(id="doc-1", content="Bryan trabajó en Itaú como Data Engineer.",
                              metadata={}, score=0.9, rerank_score=0.9)]
    return _build_prompt(query, context, language)


def test_generator_gets_an_order_naming_the_language(app_module):
    prompt = build_prompt("en")
    assert "Write 'answer' in English" in prompt
    # After the Context: placed before a long Spanish context, it lost (fef8f31).
    assert prompt.index("Write 'answer' in English") > prompt.index("Context:")
    # And nothing asks the model to work the language out from the Question.
    assert "same language as the Question" not in prompt


def test_the_order_follows_the_decision_not_the_question(app_module):
    # An English question with an explicit request for Spanish: the supervisor decided 'es'.
    prompt = build_prompt("es", query="Answer in Spanish: what did he do at Itaú?")
    assert "Write 'answer' in Spanish" in prompt
    assert "Write 'answer' in English" not in prompt


def test_generator_rejects_an_unsupported_language(app_module):
    with pytest.raises(ValueError):
        build_prompt("")
