"""Regression of the detail of internal errors (SEC-06).

Before, the exception text reached the client verbatim: server paths and Anthropic SDK
messages. Now it goes to the log, and the client only gets an identifier.
"""
import logging
import re

import pytest

from tests.api.doubles import generator_script, supervisor_script

TEMP_PATH = "/var/folders/v2/n7jcjy_11cscqrgkctpn931c0000gn/T/tmp_f3a0h9w.pdf"
PROVIDER_MESSAGE = "Error code: 401 - {'type': 'error', 'message': 'API key is invalid.'}"
GENERIC = re.compile(r"^Internal error \(([0-9a-f]{8})\)$")


def identifier(text):
    match = GENERIC.match(text)
    assert match, f"unexpected message for the client: {text!r}"
    return match.group(1)


def test_internal_failure_in_a_normal_answer(api, caplog):
    api.script(generator_script("never arrives"))
    api.fails_with(RuntimeError(f"Failed to open file '{TEMP_PATH}' as type pdf"))
    with caplog.at_level(logging.ERROR):
        r = api.client.post("/chat/", json={"query": "Where did he work?"}, headers=api.header())

    assert r.status_code == 500
    detail = r.json()["detail"]
    ident = identifier(detail)
    assert TEMP_PATH not in r.text and "Failed to open" not in r.text
    assert caplog.text.count(ident) == 1
    assert TEMP_PATH in caplog.text and "Traceback" in caplog.text


def test_internal_failure_during_the_stream(api, caplog):
    api.script(generator_script("never arrives"))
    # Fails after the first emission: the client has already received progress.
    api.fails_with(RuntimeError(PROVIDER_MESSAGE), after=1)
    with caplog.at_level(logging.ERROR):
        r = api.client.post("/chat/stream/", json={"query": "Where did he work?"}, headers=api.header())

    events = api.events(r)
    assert r.status_code == 200  # the stream had already started
    assert "error" in events[-1], events
    ident = identifier(events[-1]["error"])
    assert "API key is invalid" not in r.text and "401" not in r.text
    assert caplog.text.count(ident) == 1
    assert "API key is invalid" in caplog.text


def test_internal_failure_in_ingestion(api, caplog, monkeypatch):
    async def broken_ingestion(*args, **kwargs):
        raise RuntimeError(f"Failed to open file '{TEMP_PATH}' as type pdf")

    monkeypatch.setattr(api._ingest, "ingest_file", broken_ingestion)
    with caplog.at_level(logging.ERROR):
        r = api.client.post("/ingest/", files={"file": ("cv.pdf", b"%PDF-1.4 broken", "application/pdf")},
                            headers=api.header())

    assert r.status_code == 500
    ident = identifier(r.json()["detail"])
    assert TEMP_PATH not in r.text
    assert caplog.text.count(ident) == 1
    assert TEMP_PATH in caplog.text


# --- What must not become the generic message ---

def test_disallowed_file_type_keeps_its_message(api):
    r = api.client.post("/ingest/", files={"file": ("bad.exe", b"MZ", "application/octet-stream")},
                        headers=api.header())
    assert r.status_code == 400
    assert "File type not allowed" in r.json()["detail"]
    assert not GENERIC.match(r.json()["detail"])
    assert api.record.ingestions == []


def test_graph_without_a_final_answer_keeps_its_message(api):
    script = supervisor_script("whatever")
    script.final_state = {"intent_type": "knowledge_search", "final_answer": None, "documents": []}
    api.script(script)
    r = api.client.post("/chat/", json={"query": "Where did he work?"}, headers=api.header())
    assert r.status_code == 500
    assert r.json()["detail"] == "The agent graph did not return a final answer."


@pytest.mark.parametrize("body", [{"query": "x", "top_k_rerank": 0}, {"query": "x", "top_k_retrieve": 99}])
def test_contract_validation_is_still_422(api, body):
    r = api.client.post("/chat/", json=body, headers=api.header())
    assert r.status_code == 422
