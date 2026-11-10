"""Regression of the stream's answer on every path (BUG-09).

When the supervisor resolves the request by itself (greeting, out-of-scope topic or
tool), the graph ends without going through the generator, so nobody emits the text on
the 'custom' channel. The client was left with the progress line and nothing else.
"""
import pytest

from tests.api.doubles import SUPERVISOR_PROGRESS, generator_script, supervisor_script

CASES = [
    ("casual_greeting", "Hi! I'm the sandbox assistant, how can I help?"),
    ("out_of_scope", "That question is outside what I can answer."),
    ("tool_execution", "Tool executed (get_crypto_price)! Result:\n\nBTC: 64,200 USD"),
]


def stream(api, query="hello", **body):
    return api.client.post("/chat/stream/", json={"query": query, **body}, headers=api.header())


@pytest.mark.parametrize("intent, text", CASES)
def test_the_supervisor_resolves_and_the_stream_returns_the_answer(api, intent, text):
    api.script(supervisor_script(text, intent_type=intent))
    events = api.events(stream(api))

    final = events[-1]
    assert text in final["answer"], final
    assert final["answer"] != SUPERVISOR_PROGRESS  # the defect: progress only
    assert "confidence_score" in final and "requires_more_info" in final


@pytest.mark.parametrize("intent, text", CASES)
def test_the_supervisor_answer_is_not_duplicated(api, intent, text):
    api.script(supervisor_script(text, intent_type=intent))
    events = api.events(stream(api))
    assert events[-1]["answer"].count(text) == 1


def test_the_generator_emits_its_text_only_once(api):
    text = "He has worked at Betterfly since April 2024."
    api.script(generator_script(text, chunks=["He has worked at Betterfly ", "since April 2024."]))
    events = api.events(stream(api, query="Where did he work?"))

    final = events[-1]
    assert final["answer"].count(text) == 1, final["answer"]
    # The text arrived in chunks: there are more events than on the supervisor path.
    assert len(events) > 4


def test_the_stream_text_only_grows(api):
    # The frontend renders character diffs: an event shorter than the previous one
    # would make it lose text.
    api.script(generator_script("A long and detailed answer.", chunks=["A long ", "and detailed ", "answer."]))
    answers = [e["answer"] for e in api.events(stream(api, query="Where did he work?")) if "answer" in e]
    assert answers == sorted(answers, key=len)
    assert all(b.startswith(a) for a, b in zip(answers, answers[1:]))


def test_cache_hit_returns_a_single_event_without_running_the_graph(api):
    api.cache_returns({"answer": "Stored answer.", "sources": [], "confidence_score": 0.9,
                       "requires_more_info": False})
    events = api.events(stream(api, query="Where did he work?"))

    assert len(events) == 1
    assert events[0]["answer"] == "⚡ [CACHE HIT] Stored answer."
    assert api.graph.invocations == []
    assert api.record.cache_writes == []
