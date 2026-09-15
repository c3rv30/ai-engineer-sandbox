"""Acceso a Postgres: un pool de conexiones por proceso y conexiones con el tenant fijado.

Antes de PERF-01, cada consulta abría y cerraba su propia conexión: ~11 por pregunta,
cinco de ellas simultáneas, y el pico de conexiones escalaba con los usuarios hasta
agotar max_connections. Todos los servicios de datos pasan ahora por aquí.
"""
import asyncio
import hashlib
import hmac
import os
import uuid
from contextlib import asynccontextmanager

import asyncpg
from dotenv import load_dotenv

load_dotenv()

# Un único DSN para todo el proceso. ingestion.py usaba por defecto el superusuario
# postgres, que elude RLS; el valor por defecto es ahora el rol de la aplicación.
DB_DSN = os.getenv("DATABASE_URL", "postgresql://app_user:apppassword@localhost:5433/postgres")
POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "5"))
POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "20"))

# Clave con la que se firma el tenant que viaja a las políticas RLS (SEC-05). La misma
# vive en tenant_security.signing_key, ilegible para app_user. Sin ella no hay lectura
# posible —la firma no validaría y RLS ocultaría todo—, así que el proceso no arranca:
# es preferible a un fallo difuso de "no hay datos" en cada consulta.
TENANT_SIGNING_KEY = os.getenv("TENANT_SIGNING_KEY")
if not TENANT_SIGNING_KEY:
    raise RuntimeError(
        "TENANT_SIGNING_KEY no está configurada. Añádela a tu archivo .env "
        "(genera una con: openssl rand -hex 32) y siembra la misma clave en la base "
        "de datos con sql/migrations/apply_tenant_signing.sql."
    )
if len(TENANT_SIGNING_KEY) < 32:
    raise RuntimeError(
        "TENANT_SIGNING_KEY es demasiado corta (mínimo 32 caracteres). "
        "Genera una con: openssl rand -hex 32"
    )
_SIGNING_KEY_BYTES = TENANT_SIGNING_KEY.encode()


def sign_tenant(tenant: str) -> str:
    """Firma el tenant en la forma exacta que verifica app_current_tenant() en SQL.

    pgcrypto calcula hmac(texto, clave, 'sha256') sobre los bytes de ambas cadenas;
    aquí se hace lo mismo y se compara en hexadecimal.
    """
    return hmac.new(_SIGNING_KEY_BYTES, tenant.encode(), hashlib.sha256).hexdigest()

_pool: asyncpg.Pool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None
_pool_lock: asyncio.Lock | None = None


async def get_pool() -> asyncpg.Pool:
    """Pool del proceso, creado en la primera llamada.

    Se crea bajo demanda y no en el arranque de FastAPI porque también lo usan la CLI
    de ingesta y los scripts. Un pool de asyncpg pertenece al event loop que lo creó:
    si cambia el loop (un script que llama varias veces a asyncio.run), se crea otro.
    """
    global _pool, _pool_loop, _pool_lock
    loop = asyncio.get_running_loop()
    if _pool_loop is not loop:
        _pool, _pool_loop, _pool_lock = None, loop, asyncio.Lock()
    # Sin el lock, las cinco búsquedas que lanza asyncio.gather crearían cinco pools.
    async with _pool_lock:
        if _pool is None:
            _pool = await asyncpg.create_pool(
                DB_DSN, min_size=POOL_MIN_SIZE, max_size=POOL_MAX_SIZE, command_timeout=30,
            )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None and _pool_loop is asyncio.get_running_loop():
        await _pool.close()
    _pool = None


@asynccontextmanager
async def tenant_connection(tenant_id: uuid.UUID):
    """Conexión del pool dentro de una transacción, con el tenant fijado para RLS.

    El tenant se fija con set_config(..., true): es local a la transacción y desaparece
    con ella, así que una conexión devuelta al pool no conserva el tenant de quien la
    usó antes. Viaja como parámetro, sin interpolar en el SQL (SEC-02).

    Junto al tenant viaja su firma HMAC (SEC-05). Las políticas RLS no leen
    app.current_tenant: llaman a app_current_tenant(), que solo devuelve el tenant si la
    firma cuadra con una clave que app_user no puede leer. Una sentencia inyectada puede
    reescribir ambas variables, pero no producir una firma válida, y entonces la función
    devuelve NULL y no hay fila visible. Es el único sitio del código que fija el tenant.
    """
    tenant = str(uuid.UUID(str(tenant_id)))
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true),"
                "       set_config('app.tenant_signature', $2, true)",
                tenant, sign_tenant(tenant),
            )
            yield conn
