"""Regression of the answer language in the stored evaluation (BUG-11).

The evaluation keeps the language the supervisor decided and the one detected in the
answer, both nullable and limited to 'es' and 'en'. The evaluator writes them with its
own SQL; only the LLM judge is doubled.
"""
import secrets
import uuid
from pathlib import Path

import asyncpg
import pytest

from src.models.evaluation import RAGEvaluation
from src.models.search import SearchResult
from src.services.db import tenant_connection

TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
MIGRATION = Path(__file__).resolve().parents[2] / "sql" / "migrations" / "apply_answer_language.sql"
LANGUAGE_CHECKS = """
    SELECT count(*) FROM pg_constraint
    WHERE conrelid = 'rag_evaluations'::regclass AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%_language%'
"""


@pytest.fixture
async def mark(superuser):
    """A query text impossible to guess, and its rows deleted at the end."""
    value = f"language test {secrets.token_hex(6)}"
    yield value
    await superuser.execute("DELETE FROM rag_evaluations WHERE query = $1", value)


async def insert(conn, query, expected, detected):
    await conn.execute(
        "INSERT INTO rag_evaluations (tenant_id, query, expected_language, detected_language) VALUES ($1, $2, $3, $4)",
        TENANT, query, expected, detected,
    )


@pytest.mark.parametrize("expected, detected", [("en", "es"), ("es", "es"), ("en", None), (None, None)])
async def test_application_role_stores_both_languages(mark, expected, detected):
    async with tenant_connection(TENANT) as conn:
        await insert(conn, mark, expected, detected)
        row = await conn.fetchrow(
            "SELECT expected_language, detected_language FROM rag_evaluations WHERE query = $1", mark)
    assert (row["expected_language"], row["detected_language"]) == (expected, detected)


@pytest.mark.parametrize("expected, detected", [("pt", None), (None, "English"), ("", "es")])
async def test_only_spanish_or_english(mark, expected, detected):
    with pytest.raises(asyncpg.CheckViolationError):
        async with tenant_connection(TENANT) as conn:
            await insert(conn, mark, expected, detected)


async def test_migration_adds_the_columns_to_an_old_table(superuser):
    # Inside a transaction that is rolled back: in Postgres the DDL is transactional.
    tx = superuser.transaction()
    await tx.start()
    try:
        await superuser.execute("ALTER TABLE rag_evaluations DROP COLUMN expected_language, DROP COLUMN detected_language")
        await superuser.execute(MIGRATION.read_text())
        columns = await superuser.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'rag_evaluations' AND column_name LIKE '%_language'")
        assert {c["column_name"] for c in columns} == {"expected_language", "detected_language"}
        assert await superuser.fetchval(LANGUAGE_CHECKS) == 2
    finally:
        await tx.rollback()


async def test_migration_is_idempotent(superuser):
    before = await superuser.fetchval(LANGUAGE_CHECKS)
    await superuser.execute(MIGRATION.read_text())
    assert before == 2
    assert await superuser.fetchval(LANGUAGE_CHECKS) == before


async def test_evaluator_stores_the_languages(monkeypatch, mark, superuser):
    from src.services import evaluator

    class Judge:
        """Stands in for the Instructor client: only messages.create is used."""
        def __init__(self):
            self.messages = self

        async def create(self, *args, **kwargs):
            return RAGEvaluation(faithfulness_score=0.9, relevance_score=0.8,
                                 context_precision_score=0.7, reasoning="double")

    monkeypatch.setattr(evaluator, "client", Judge())
    context = [SearchResult(id="doc-1", content="Bryan trabajó en Itaú.", metadata={}, score=0.9)]
    await evaluator.evaluate_rag_response(TENANT, mark, "Bryan worked at Itaú.", context,
                                          expected_language="en", detected_language="es")

    row = await superuser.fetchrow(
        "SELECT expected_language, detected_language, relevance_score FROM rag_evaluations WHERE query = $1", mark)
    # Without a row, the evaluator swallowed an error: it only prints it.
    assert row is not None
    assert (row["expected_language"], row["detected_language"], row["relevance_score"]) == ("en", "es", 0.8)
