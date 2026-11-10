"""Regression of the answer language (BUG-11).

The supervisor decides the language with a closed field, and the generator gets an
order naming it instead of a rule to work out. These modules create LLM clients on
import, which is why the checks live in this layer and not in tests/unit/.
"""
import logging

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


# --- Safety net at the endpoints: a signal, never a gate ---

ENGLISH = ("Bryan worked at Itaú as a Data Engineer between 2019 and 2021, where he designed "
           "data pipelines with Airflow and Spark.")
SPANISH = ("Bryan trabajó en Itaú como Data Engineer entre 2019 y 2021, donde diseñó "
           "pipelines de datos con Airflow y Spark.")
MISMATCH = "Answer language mismatch"


def ask(api, endpoint):
    r = api.client.post(endpoint, json={"query": "What did he do at Itaú?"}, headers=api.header())
    assert r.status_code == 200
    return api.events(r) if endpoint.endswith("stream/") else r.json()


@pytest.mark.parametrize("endpoint", ["/chat/", "/chat/stream/"])
def test_mismatch_is_logged_and_not_cached(api, caplog, endpoint):
    from tests.api.doubles import generator_script

    api.script(generator_script(SPANISH, language="en"))
    with caplog.at_level(logging.WARNING):
        got = ask(api, endpoint)

    # The client gets the answer as it came, with no notice and no retry.
    final = got[-1] if isinstance(got, list) else got
    assert SPANISH in final["answer"] and "error" not in final
    assert caplog.text.count(MISMATCH) == 1
    assert "expected=en detected=es" in caplog.text
    assert api.record.cache_writes == []
    assert api.record.evaluation_languages == [("en", "es")]


@pytest.mark.parametrize("endpoint", ["/chat/", "/chat/stream/"])
def test_matching_answer_is_cached_as_before(api, caplog, endpoint):
    from tests.api.doubles import generator_script

    api.script(generator_script(ENGLISH, language="en"))
    with caplog.at_level(logging.WARNING):
        ask(api, endpoint)

    assert MISMATCH not in caplog.text
    assert len(api.record.cache_writes) == 1
    assert api.record.evaluation_languages == [("en", "en")]


def test_mismatch_does_not_change_the_stream(api):
    # The same script with the matching decision: the events must be identical.
    from tests.api.doubles import generator_script

    api.script(generator_script(SPANISH, language="en"))
    mismatched = ask(api, "/chat/stream/")
    api.script(generator_script(SPANISH, language="es"))
    matching = ask(api, "/chat/stream/")
    assert mismatched == matching


@pytest.mark.parametrize("endpoint", ["/chat/", "/chat/stream/"])
def test_tool_answer_is_not_checked(api, caplog, endpoint):
    from tests.api.doubles import supervisor_script

    # A Spanish question answered with the fixed English template.
    api.script(supervisor_script("Tool executed (get_current_time)! Result:\n\nThe current time is 10:42.",
                                 intent_type="tool_execution", language="es"))
    with caplog.at_level(logging.WARNING):
        ask(api, endpoint)
    assert MISMATCH not in caplog.text


@pytest.mark.parametrize("endpoint", ["/chat/", "/chat/stream/"])
def test_a_failing_detector_does_not_break_the_answer(api, monkeypatch, caplog, endpoint):
    from tests.api.doubles import generator_script

    def broken(*args, **kwargs):
        raise RuntimeError("detector failed")

    monkeypatch.setattr(api._chat, "check_answer_language", broken)
    api.script(generator_script(ENGLISH, language="en"))
    got = ask(api, endpoint)
    final = got[-1] if isinstance(got, list) else got
    assert ENGLISH in final["answer"] and "error" not in final
    assert "Answer language check failed" in caplog.text
