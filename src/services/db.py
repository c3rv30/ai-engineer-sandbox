"""Acceso a Postgres: un pool de conexiones por proceso y conexiones con el tenant fijado.

Antes de PERF-01, cada consulta abría y cerraba su propia conexión: ~11 por pregunta,
cinco de ellas simultáneas, y el pico de conexiones escalaba con los usuarios hasta
agotar max_connections. Todos los servicios de datos pasan ahora por aquí.
"""
import asyncio
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

    Es el único sitio del código que fija el tenant: el endurecimiento pendiente de
    SEC-05 (que una sentencia inyectada no pueda reescribirlo) se aplica aquí.
    """
    tenant = str(uuid.UUID(str(tenant_id)))
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            yield conn
