"""La base se crea desde volumen vacío con los scripts de sql/ (BUG-04)."""

TABLAS = {"documents", "knowledge_graph", "semantic_cache", "user_memory", "rag_evaluations"}


async def test_base_recien_creada(superuser):
    tablas = {r["relname"] for r in await superuser.fetch(
        "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'")}
    assert tablas == TABLAS

    forzadas = await superuser.fetch(
        "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace"
        " AND relkind = 'r' AND relrowsecurity AND relforcerowsecurity")
    assert {r["relname"] for r in forzadas} == TABLAS

    politicas = await superuser.fetch("SELECT tablename, qual FROM pg_policies WHERE schemaname = 'public'")
    assert {r["tablename"] for r in politicas} == TABLAS
    assert all("app_current_tenant()" in r["qual"] for r in politicas)

    assert await superuser.fetchval("SELECT count(*) FROM tenant_security.signing_key") == 1
    assert await superuser.fetchval("SELECT rolname FROM pg_roles WHERE rolname = 'app_user'") == "app_user"


async def test_la_base_de_pruebas_esta_vacia(superuser):
    for tabla in TABLAS:
        assert await superuser.fetchval(f"SELECT count(*) FROM {tabla}") == 0, tabla
