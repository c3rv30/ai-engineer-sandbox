"""API layer: the full application with TestClient and doubles for the graph and the services.

It does not connect to PostgreSQL or call any LLM, so it does not need Docker.
Authentication is the real one: the 401s of SEC-01 and SEC-02 would be meaningless with a double.
"""
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.api.doubles import GraphDouble, Script

API_DIR = __file__.rsplit("/", 1)[0]
TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if str(item.path).startswith(API_DIR):
            item.add_marker(pytest.mark.api)


@dataclass
class Record:
    """What each doubled service was called with."""
    cache_reads: list[tuple] = field(default_factory=list)
    cache_writes: list[tuple] = field(default_factory=list)
    memory_reads: list[tuple] = field(default_factory=list)
    saved_facts: list[tuple] = field(default_factory=list)
    evaluations: list[tuple] = field(default_factory=list)
    # (expected, detected) of each evaluation, in the same order (BUG-11).
    evaluation_languages: list[tuple] = field(default_factory=list)
    ingestions: list[tuple] = field(default_factory=list)


@dataclass
class Api:
    """HTTP client, installed doubles and helpers to build tokens."""
    client: TestClient
    record: Record
    graph: GraphDouble
    _chat: Any
    _ingest: Any

    def script(self, script: Script):
        self.graph.script = script
        return self.graph

    def fails_with(self, error: Exception, *, after: int = 0):
        self.graph.error = error
        self.graph.error_after = after
        return self.graph

    def header(self, *, tenant=TENANT, user="bryan", key=None, no_sub=False, no_tenant=False):
        import os
        from datetime import datetime, timedelta, timezone

        import jwt

        payload: dict[str, Any] = {"exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
        if not no_sub:
            payload["sub"] = user
        if not no_tenant:
            payload["tenant_id"] = str(tenant)
        token = jwt.encode(payload, key or os.environ["JWT_SECRET_KEY"], algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def cache_returns(self, data: dict):
        self._cache_response[0] = data

    def events(self, response) -> list[dict]:
        """The JSON objects of an SSE stream, in order."""
        import json

        return [json.loads(l[len("data: "):], strict=False)
                for l in response.text.splitlines() if l.startswith("data: ")]


@pytest.fixture(autouse=True)
def no_postgres(monkeypatch):
    """No test in this layer may open a connection to PostgreSQL.

    The data services are doubled, so a connection means something escaped the double.
    Without this guard, the test would pass anyway with the development database
    running and fail only on a machine without it.
    """
    import asyncpg

    def forbidden(*args, **kwargs):
        raise AssertionError("the API layer must not connect to PostgreSQL")

    monkeypatch.setattr(asyncpg, "connect", forbidden)
    monkeypatch.setattr(asyncpg, "create_pool", forbidden)


@pytest.fixture(scope="session")
def app_module():
    """Imports the application once per session: it costs ~10 s (models and clients).

    It also disables the telemetry of onnxruntime, which comes with FlashRank. Its
    events thread processes HTTP responses while the interpreter is already shutting
    down and aborts the process (code 134, "recursive_mutex lock failed"), after every
    test has passed: the full suite failed that way ~7 of every 8 runs.
    """
    from src.api import main

    return main


@pytest.fixture
def api(monkeypatch, app_module):
    from src.api.routers import chat as chat_mod
    from src.api.routers import ingest as ingest_mod

    record = Record()
    cache_response: list[Any] = [None]

    async def check_semantic_cache(tenant_id, query, *args, **kwargs):
        record.cache_reads.append((tenant_id, query))
        return cache_response[0]

    async def save_semantic_cache(tenant_id, query, response_dict, *args, **kwargs):
        record.cache_writes.append((tenant_id, query, response_dict))

    async def retrieve_user_facts(tenant_id, query, *args, **kwargs):
        record.memory_reads.append((tenant_id, query))
        return ""

    async def extract_and_save_facts(tenant_id, user_message, *args, **kwargs):
        record.saved_facts.append((tenant_id, user_message))

    async def evaluate_rag_response(tenant_id, query, answer, context, *args, **kwargs):
        record.evaluations.append((tenant_id, query, answer, context))
        record.evaluation_languages.append((kwargs.get("expected_language"), kwargs.get("detected_language")))

    async def ingest_file(path, tenant_id, *args, **kwargs):
        record.ingestions.append((path, tenant_id, kwargs.get("source")))
        return {"chunks_ingested": 1, "message": "ok"}

    graph = GraphDouble()
    monkeypatch.setattr(chat_mod, "agent_graph", graph)
    monkeypatch.setattr(chat_mod, "check_semantic_cache", check_semantic_cache)
    monkeypatch.setattr(chat_mod, "save_semantic_cache", save_semantic_cache)
    monkeypatch.setattr(chat_mod, "retrieve_user_facts", retrieve_user_facts)
    monkeypatch.setattr(chat_mod, "extract_and_save_facts", extract_and_save_facts)
    monkeypatch.setattr(chat_mod, "evaluate_rag_response", evaluate_rag_response)
    monkeypatch.setattr(ingest_mod, "ingest_file", ingest_file)

    # No context manager on purpose: that way the lifespan does not run and the layer
    # does not try to open the Postgres pool.
    client = TestClient(app_module.app)
    obj = Api(client=client, record=record, graph=graph, _chat=chat_mod, _ingest=ingest_mod)
    obj._cache_response = cache_response
    yield obj
    client.close()
