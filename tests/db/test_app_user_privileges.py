"""Regresión de los privilegios del rol de la aplicación (HYG-07, SEC-07)."""
import asyncpg
import pytest


async def test_tabla_nueva_en_public_no_es_legible_para_app_user(superuser):
    # Dentro de una transacción que se deshace: la tabla nunca llega a existir.
    tx = superuser.transaction()
    await tx.start()
    try:
        await superuser.execute("CREATE TABLE public.hyg07_secreta (dato TEXT)")
        await superuser.execute("REVOKE ALL ON TABLE public.hyg07_secreta FROM PUBLIC")
        assert await superuser.fetchval("SELECT has_table_privilege('app_user', 'public.hyg07_secreta', 'SELECT')") is False
        await superuser.execute("SET LOCAL ROLE app_user")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await superuser.fetch("SELECT * FROM public.hyg07_secreta")
    finally:
        await tx.rollback()


async def test_app_user_no_puede_crear_esquemas(app_user_conn):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_user_conn.execute("CREATE SCHEMA sombra")


async def test_app_user_sin_ajustes_propios_guardados(superuser):
    # Un search_path hacia un esquema propio desviaba las consultas de la aplicación
    # (SEC-07); un default_transaction_read_only bloqueaba sus escrituras.
    ajustes = await superuser.fetch(
        "SELECT setdatabase, setconfig FROM pg_db_role_setting WHERE setrole = 'app_user'::regrole")
    assert ajustes == []


async def test_app_user_no_lee_la_clave_de_firma(app_user_conn):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_user_conn.fetch("SELECT key FROM tenant_security.signing_key")
