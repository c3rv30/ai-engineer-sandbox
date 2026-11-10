"""Regression of the application role's privileges (HYG-07, SEC-07)."""
import asyncpg
import pytest


async def test_new_table_in_public_is_not_readable_by_app_user(superuser):
    # Inside a transaction that is rolled back: the table never comes to exist.
    tx = superuser.transaction()
    await tx.start()
    try:
        await superuser.execute("CREATE TABLE public.hyg07_secret (data TEXT)")
        await superuser.execute("REVOKE ALL ON TABLE public.hyg07_secret FROM PUBLIC")
        assert await superuser.fetchval("SELECT has_table_privilege('app_user', 'public.hyg07_secret', 'SELECT')") is False
        await superuser.execute("SET LOCAL ROLE app_user")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await superuser.fetch("SELECT * FROM public.hyg07_secret")
    finally:
        await tx.rollback()


async def test_app_user_cannot_create_schemas(app_user_conn):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_user_conn.execute("CREATE SCHEMA shadow")


async def test_app_user_has_no_stored_settings_of_its_own(superuser):
    # A search_path pointing at its own schema diverted the application's queries
    # (SEC-07); a default_transaction_read_only blocked its writes.
    settings = await superuser.fetch(
        "SELECT setdatabase, setconfig FROM pg_db_role_setting WHERE setrole = 'app_user'::regrole")
    assert settings == []


async def test_app_user_cannot_read_the_signing_key(app_user_conn):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_user_conn.fetch("SELECT key FROM tenant_security.signing_key")
