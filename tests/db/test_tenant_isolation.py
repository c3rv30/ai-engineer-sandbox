"""Regresión del aislamiento entre tenants (SEC-05, SEC-03, PERF-01).

Todo contra la base desechable: se siembra como superusuario y se comprueba como
app_user a través del código real de la aplicación. Cada comprobación de que un tenant
no ve algo va acompañada de un control positivo desde el tenant dueño, para que un "0
filas" no pueda deberse a que no había nada que ver.
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
async def documentos(superuser):
    """Un documento por tenant, con un contenido imposible de adivinar."""
    marca = secrets.token_hex(6)
    contenidos = {TENANT_A: f"ciudad inventada Zorvania-{marca}", TENANT_B: f"ciudad inventada Quelmar-{marca}"}
    for tenant, contenido in contenidos.items():
        await superuser.execute("INSERT INTO documents (tenant_id, content) VALUES ($1, $2)", tenant, contenido)
    yield contenidos
    await superuser.execute("DELETE FROM documents WHERE content = ANY($1::text[])", list(contenidos.values()))


async def contenidos_visibles(conn, contenidos):
    filas = await conn.fetch("SELECT content FROM documents WHERE content = ANY($1::text[])", list(contenidos.values()))
    return {r["content"] for r in filas}


# --- Contexto firmado (SEC-05) ---

async def test_contexto_firmado_valido_ve_solo_su_tenant(documentos):
    async with tenant_connection(TENANT_A) as conn:
        assert await contenidos_visibles(conn, documentos) == {documentos[TENANT_A]}
    # Control positivo: el otro tenant ve lo suyo.
    async with tenant_connection(TENANT_B) as conn:
        assert await contenidos_visibles(conn, documentos) == {documentos[TENANT_B]}


async def test_contexto_sin_firma_no_ve_nada(documentos, app_user_conn):
    async with app_user_conn.transaction():
        await app_user_conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(TENANT_A))
        assert await contenidos_visibles(app_user_conn, documentos) == set()


async def test_contexto_con_firma_falsa_no_ve_nada(documentos, app_user_conn):
    async with app_user_conn.transaction():
        await app_user_conn.execute(
            "SELECT set_config('app.current_tenant', $1, true), set_config('app.tenant_signature', $2, true)",
            str(TENANT_A), secrets.token_hex(32),
        )
        assert await contenidos_visibles(app_user_conn, documentos) == set()


async def test_firma_de_un_tenant_no_vale_para_otro(documentos, app_user_conn):
    async with app_user_conn.transaction():
        await app_user_conn.execute(
            "SELECT set_config('app.current_tenant', $1, true), set_config('app.tenant_signature', $2, true)",
            str(TENANT_B), sign_tenant(str(TENANT_A)),
        )
        assert await contenidos_visibles(app_user_conn, documentos) == set()


async def test_tenant_reescrito_desde_la_propia_sentencia(documentos):
    # El payload de SEC-05: el FROM de la segunda rama reescribe el tenant antes de
    # recorrer la tabla. Con políticas que leían current_setting, devolvía filas ajenas.
    async with tenant_connection(TENANT_A) as conn:
        filas = await conn.fetch(
            "SELECT content FROM documents WHERE content = $1"
            " UNION SELECT content FROM (SELECT set_config('app.current_tenant', $2, false)) s, documents",
            documentos[TENANT_A], str(TENANT_B),
        )
    assert documentos[TENANT_B] not in {r["content"] for r in filas}
    # Control positivo: la sentencia sí devuelve lo propio.
    assert documentos[TENANT_A] in {r["content"] for r in filas}


async def test_firma_coincide_con_la_de_la_base(superuser):
    tenant = str(TENANT_A)
    en_la_base = await superuser.fetchval(
        "SELECT encode(hmac($1::text, key, 'sha256'), 'hex') FROM tenant_security.signing_key", tenant)
    assert sign_tenant(tenant) == en_la_base


# --- GraphRAG (SEC-03) ---

@pytest.fixture
async def grafo(superuser):
    """Tripletas solo en TENANT_B; TENANT_A no tiene grafo."""
    marca = secrets.token_hex(4)
    nodos = [(f"kestrelio{marca}", "trabaja_en", f"montevarro{marca}"), (f"montevarro{marca}", "usa", f"pgvector{marca}")]
    for origen, relacion, destino in nodos:
        await superuser.execute(
            "INSERT INTO knowledge_graph (tenant_id, source_node, relation, target_node) VALUES ($1, $2, $3, $4)",
            TENANT_B, origen, relacion, destino)
    yield marca
    await superuser.execute("DELETE FROM knowledge_graph WHERE source_node LIKE $1", f"%{marca}")


@pytest.fixture
def tokenizador_permisivo(monkeypatch):
    """Toda la pregunta como una sola palabra, comillas incluidas.

    Es el escenario que SEC-03 anticipa: un cambio en el regex que deje pasar
    puntuación. Con el tokenizador real, las comillas nunca llegan al SQL.
    """
    original = re.findall

    def findall(patron, texto, *args, **kwargs):
        if patron == r"\w+":
            return [texto]
        return original(patron, texto, *args, **kwargs)

    monkeypatch.setattr(re, "findall", findall)


async def test_graphrag_control_positivo(grafo):
    assert f"kestrelio{grafo}" in await retrieve_subgraph(TENANT_B, f"¿Dónde trabaja kestrelio{grafo}?")
    assert await retrieve_subgraph(TENANT_A, f"¿Dónde trabaja kestrelio{grafo}?") == ""


async def test_graphrag_lectura_entre_tenants(grafo, tokenizador_permisivo):
    payload = (f"zzqx%' or true union select source_node, relation, target_node from "
               f"(select set_config('app.current_tenant', '{TENANT_B}', false)) s, knowledge_graph --")
    assert await retrieve_subgraph(TENANT_A, payload) == ""


async def test_graphrag_tautologia(grafo, tokenizador_permisivo):
    # Desde el dueño del grafo, con una palabra que no coincide con ningún nodo.
    assert await retrieve_subgraph(TENANT_B, "zzqx%' or true or source_node ilike '%zzqx") == ""


async def test_graphrag_apostrofo(grafo, tokenizador_permisivo):
    # Con concatenación, "o'brien" rompía el SQL y el investigador caía.
    assert await retrieve_subgraph(TENANT_B, "o'brien") == ""


# --- Pool (PERF-01) ---

async def test_conexion_reutilizada_del_pool_no_conserva_el_tenant(documentos):
    async with tenant_connection(TENANT_A) as conn:
        pid = await conn.fetchval("SELECT pg_backend_pid()")
        assert await contenidos_visibles(conn, documentos) == {documentos[TENANT_A]}

    pool = await get_pool()
    for _ in range(pool.get_max_size()):
        async with pool.acquire() as conn:
            if await conn.fetchval("SELECT pg_backend_pid()") != pid:
                continue
            assert await conn.fetchval("SELECT current_setting('app.current_tenant', true)") in (None, "")
            assert await conn.fetchval("SELECT current_setting('app.tenant_signature', true)") in (None, "")
            assert await contenidos_visibles(conn, documentos) == set()
            return
    pytest.fail(f"no se pudo volver a obtener la conexión {pid} del pool")


async def test_contexto_local_a_la_transaccion(documentos, monkeypatch):
    # Sin el RESET ALL que asyncpg ejecuta al devolver la conexión: así se comprueba la
    # defensa propia de tenant_connection (set_config local), no la del pool.
    from src.services import db
    async def sin_reset(conn):
        pass

    pool = await asyncpg.create_pool(db.DB_DSN, min_size=1, max_size=1, reset=sin_reset)
    try:
        async def pool_sin_reset():
            return pool
        monkeypatch.setattr(db, "get_pool", pool_sin_reset)
        async with db.tenant_connection(TENANT_A) as conn:
            assert await contenidos_visibles(conn, documentos) == {documentos[TENANT_A]}
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT current_setting('app.current_tenant', true)") in (None, "")
            assert await conn.fetchval("SELECT current_setting('app.tenant_signature', true)") in (None, "")
            assert await contenidos_visibles(conn, documentos) == set()
    finally:
        await pool.close()
