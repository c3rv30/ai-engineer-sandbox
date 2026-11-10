"""The database is created from an empty volume with the sql/ scripts (BUG-04)."""

TABLES = {"documents", "knowledge_graph", "semantic_cache", "user_memory", "rag_evaluations"}


async def test_freshly_created_database(superuser):
    tables = {r["relname"] for r in await superuser.fetch(
        "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'")}
    assert tables == TABLES

    forced = await superuser.fetch(
        "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace"
        " AND relkind = 'r' AND relrowsecurity AND relforcerowsecurity")
    assert {r["relname"] for r in forced} == TABLES

    policies = await superuser.fetch("SELECT tablename, qual FROM pg_policies WHERE schemaname = 'public'")
    assert {r["tablename"] for r in policies} == TABLES
    assert all("app_current_tenant()" in r["qual"] for r in policies)

    assert await superuser.fetchval("SELECT count(*) FROM tenant_security.signing_key") == 1
    assert await superuser.fetchval("SELECT rolname FROM pg_roles WHERE rolname = 'app_user'") == "app_user"


async def test_the_test_database_is_empty(superuser):
    for table in TABLES:
        assert await superuser.fetchval(f"SELECT count(*) FROM {table}") == 0, table
