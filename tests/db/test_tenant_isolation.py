"""Regression of tenant isolation (SEC-05, SEC-03, PERF-01).

All against the disposable database: seeded as superuser and checked as app_user
through the application's real code. Every check that a tenant does not see something
comes with a positive control from the owning tenant, so that "0 rows" cannot be down
to there being nothing to see.
"""
import re
import secrets
import uuid

import asyncpg
import pytest

from src.services.db import get_pool, sign_tenant, tenant_connection
from src.services.graphrag import retrieve_subgraph

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
async def documents(superuser):
    """One document per tenant, with content impossible to guess."""
    mark = secrets.token_hex(6)
    contents = {TENANT_A: f"made-up city Zorvania-{mark}", TENANT_B: f"made-up city Quelmar-{mark}"}
    for tenant, content in contents.items():
        await superuser.execute("INSERT INTO documents (tenant_id, content) VALUES ($1, $2)", tenant, content)
    yield contents
    await superuser.execute("DELETE FROM documents WHERE content = ANY($1::text[])", list(contents.values()))


async def visible_contents(conn, contents):
    rows = await conn.fetch("SELECT content FROM documents WHERE content = ANY($1::text[])", list(contents.values()))
    return {r["content"] for r in rows}


# --- Signed context (SEC-05) ---

async def test_valid_signed_context_sees_only_its_tenant(documents):
    async with tenant_connection(TENANT_A) as conn:
        assert await visible_contents(conn, documents) == {documents[TENANT_A]}
    # Positive control: the other tenant sees its own.
    async with tenant_connection(TENANT_B) as conn:
        assert await visible_contents(conn, documents) == {documents[TENANT_B]}


async def test_unsigned_context_sees_nothing(documents, app_user_conn):
    async with app_user_conn.transaction():
        await app_user_conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(TENANT_A))
        assert await visible_contents(app_user_conn, documents) == set()


async def test_context_with_a_fake_signature_sees_nothing(documents, app_user_conn):
    async with app_user_conn.transaction():
        await app_user_conn.execute(
            "SELECT set_config('app.current_tenant', $1, true), set_config('app.tenant_signature', $2, true)",
            str(TENANT_A), secrets.token_hex(32),
        )
        assert await visible_contents(app_user_conn, documents) == set()


async def test_one_tenant_signature_is_not_valid_for_another(documents, app_user_conn):
    async with app_user_conn.transaction():
        await app_user_conn.execute(
            "SELECT set_config('app.current_tenant', $1, true), set_config('app.tenant_signature', $2, true)",
            str(TENANT_B), sign_tenant(str(TENANT_A)),
        )
        assert await visible_contents(app_user_conn, documents) == set()


async def test_tenant_rewritten_from_the_statement_itself(documents):
    # The SEC-05 payload: the FROM of the second branch rewrites the tenant before
    # scanning the table. With policies that read current_setting, it returned foreign rows.
    async with tenant_connection(TENANT_A) as conn:
        rows = await conn.fetch(
            "SELECT content FROM documents WHERE content = $1"
            " UNION SELECT content FROM (SELECT set_config('app.current_tenant', $2, false)) s, documents",
            documents[TENANT_A], str(TENANT_B),
        )
    assert documents[TENANT_B] not in {r["content"] for r in rows}
    # Positive control: the statement does return its own.
    assert documents[TENANT_A] in {r["content"] for r in rows}


async def test_signature_matches_the_database_one(superuser):
    tenant = str(TENANT_A)
    in_the_database = await superuser.fetchval(
        "SELECT encode(hmac($1::text, key, 'sha256'), 'hex') FROM tenant_security.signing_key", tenant)
    assert sign_tenant(tenant) == in_the_database


# --- GraphRAG (SEC-03) ---

@pytest.fixture
async def graph(superuser):
    """Triples only in TENANT_B; TENANT_A has no graph."""
    mark = secrets.token_hex(4)
    nodes = [(f"kestrelio{mark}", "works_at", f"montevarro{mark}"), (f"montevarro{mark}", "uses", f"pgvector{mark}")]
    for source, relation, target in nodes:
        await superuser.execute(
            "INSERT INTO knowledge_graph (tenant_id, source_node, relation, target_node) VALUES ($1, $2, $3, $4)",
            TENANT_B, source, relation, target)
    yield mark
    await superuser.execute("DELETE FROM knowledge_graph WHERE source_node LIKE $1", f"%{mark}")


@pytest.fixture
def permissive_tokenizer(monkeypatch):
    """The whole question as a single word, quotes included.

    It is the scenario SEC-03 anticipates: a regex change that lets punctuation
    through. With the real tokenizer, quotes never reach the SQL.
    """
    original = re.findall

    def findall(pattern, text, *args, **kwargs):
        if pattern == r"\w+":
            return [text]
        return original(pattern, text, *args, **kwargs)

    monkeypatch.setattr(re, "findall", findall)


async def test_graphrag_positive_control(graph):
    assert f"kestrelio{graph}" in await retrieve_subgraph(TENANT_B, f"Where does kestrelio{graph} work?")
    assert await retrieve_subgraph(TENANT_A, f"Where does kestrelio{graph} work?") == ""


async def test_graphrag_cross_tenant_read(graph, permissive_tokenizer):
    payload = (f"zzqx%' or true union select source_node, relation, target_node from "
               f"(select set_config('app.current_tenant', '{TENANT_B}', false)) s, knowledge_graph --")
    assert await retrieve_subgraph(TENANT_A, payload) == ""


async def test_graphrag_tautology(graph, permissive_tokenizer):
    # From the graph's owner, with a word that matches no node.
    assert await retrieve_subgraph(TENANT_B, "zzqx%' or true or source_node ilike '%zzqx") == ""


async def test_graphrag_apostrophe(graph, permissive_tokenizer):
    # With concatenation, "o'brien" broke the SQL and the researcher went down.
    assert await retrieve_subgraph(TENANT_B, "o'brien") == ""


# --- Pool (PERF-01) ---

async def test_connection_reused_from_the_pool_does_not_keep_the_tenant(documents):
    async with tenant_connection(TENANT_A) as conn:
        pid = await conn.fetchval("SELECT pg_backend_pid()")
        assert await visible_contents(conn, documents) == {documents[TENANT_A]}

    pool = await get_pool()
    for _ in range(pool.get_max_size()):
        async with pool.acquire() as conn:
            if await conn.fetchval("SELECT pg_backend_pid()") != pid:
                continue
            assert await conn.fetchval("SELECT current_setting('app.current_tenant', true)") in (None, "")
            assert await conn.fetchval("SELECT current_setting('app.tenant_signature', true)") in (None, "")
            assert await visible_contents(conn, documents) == set()
            return
    pytest.fail(f"could not get connection {pid} back from the pool")


async def test_context_local_to_the_transaction(documents, monkeypatch):
    # Without the RESET ALL asyncpg runs when returning the connection: this checks
    # tenant_connection's own defense (local set_config), not the pool's.
    from src.services import db
    async def no_reset(conn):
        pass

    pool = await asyncpg.create_pool(db.DB_DSN, min_size=1, max_size=1, reset=no_reset)
    try:
        async def pool_without_reset():
            return pool
        monkeypatch.setattr(db, "get_pool", pool_without_reset)
        async with db.tenant_connection(TENANT_A) as conn:
            assert await visible_contents(conn, documents) == {documents[TENANT_A]}
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT current_setting('app.current_tenant', true)") in (None, "")
            assert await conn.fetchval("SELECT current_setting('app.tenant_signature', true)") in (None, "")
            assert await visible_contents(conn, documents) == set()
    finally:
        await pool.close()
