"""Regression of the object stored in the cache (BUG-01).

The SSE generator accumulates each node's progress messages into the text the client
sees. That text must not end up in the cache or in the evaluator: what is stored is the
clean structured answer.
"""
from tests.api.doubles import (
    RESEARCHER_PROGRESS, SUPERVISOR_PROGRESS, GENERATOR_PREFIX, document, generator_script,
)

TEXT = "He has worked at Betterfly since April 2024."
PROGRESS = [SUPERVISOR_PROGRESS.strip(), RESEARCHER_PROGRESS.strip(), GENERATOR_PREFIX.strip()]


def stream(api, **body):
    request = {"query": "Where did he work?", **body}
    return api.client.post("/chat/stream/", json=request, headers=api.header())


def test_what_is_stored_carries_no_progress_messages(api):
    api.script(generator_script(TEXT, chunks=["He has worked at Betterfly ", "since April 2024."]))
    r = stream(api)
    events = api.events(r)

    # What the client sees does carry the progress: it is what the interface renders.
    emitted = events[-1]["answer"]
    assert all(mark in emitted for mark in PROGRESS), emitted
    assert TEXT in emitted

    # What is sent to storage does not.
    assert len(api.record.cache_writes) == 1
    stored = api.record.cache_writes[0][2]
    assert stored["answer"] == TEXT
    for mark in PROGRESS:
        assert mark not in stored["answer"]
    assert stored["confidence_score"] == 0.9 and stored["requires_more_info"] is False


def test_the_evaluator_gets_the_clean_answer(api):
    docs = [document("Betterfly, 2024", id_="doc-9")]
    api.script(generator_script(TEXT, documents=docs))
    stream(api)

    assert len(api.record.evaluations) == 1
    _, query, evaluated_answer, context = api.record.evaluations[0]
    assert query == "Where did he work?"
    assert evaluated_answer == TEXT
    for mark in PROGRESS:
        assert mark not in evaluated_answer
    assert [d.id for d in context] == ["doc-9"]


def test_memory_gets_the_user_question(api):
    api.script(generator_script(TEXT))
    stream(api)
    assert api.record.saved_facts == [(api.graph.invocations[0]["tenant_id"], "Where did he work?")]


def test_non_cacheable_answer_is_not_stored(api):
    # requires_more_info=True: the system itself considers it insufficient (BUG-02).
    api.script(generator_script(TEXT, needs_more=True))
    stream(api)
    assert api.record.cache_writes == []


def test_request_with_history_neither_reads_nor_writes_the_cache(api):
    api.script(generator_script(TEXT))
    stream(api, history=[{"role": "user", "content": "Did he work at Betterfly?"},
                         {"role": "assistant", "content": "Yes."}])
    assert api.record.cache_reads == []
    assert api.record.cache_writes == []


def test_normal_answer_also_stores_the_clean_object(api):
    api.script(generator_script(TEXT))
    r = api.client.post("/chat/", json={"query": "Where did he work?"}, headers=api.header())
    assert r.status_code == 200
    assert r.json()["answer"] == TEXT
    assert api.record.cache_writes[0][2]["answer"] == TEXT
