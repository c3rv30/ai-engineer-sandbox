"""The layer does not touch PostgreSQL: the data services are doubled."""
import asyncio

import asyncpg
import pytest

from tests.api.doubles import generator_script


def test_the_connection_guard_is_active(api):
    # Control of the guard itself: if a test tried to connect, it would fail here.
    with pytest.raises(AssertionError, match="must not connect"):
        asyncio.run(asyncpg.connect("postgresql://app_user:apppassword@127.0.0.1:5439/postgres"))
    with pytest.raises(AssertionError, match="must not connect"):
        asyncio.run(asyncpg.create_pool("postgresql://app_user:apppassword@127.0.0.1:5439/postgres"))


def test_a_full_request_opens_no_connections(api):
    api.script(generator_script("Answer without a database."))
    r = api.client.post("/chat/", json={"query": "Where did he work?"}, headers=api.header())
    assert r.status_code == 200
    # The doubled services recorded the calls that would have gone to Postgres.
    assert api.record.cache_reads and api.record.memory_reads
