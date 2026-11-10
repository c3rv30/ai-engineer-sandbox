"""Postgres access: one connection pool per process and connections with the tenant set.

Before PERF-01, every query opened and closed its own connection: ~11 per question,
five of them simultaneous, and the connection peak scaled with users until it exhausted
max_connections. Every data service now goes through here.
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

# A single DSN for the whole process. ingestion.py used to default to the postgres
# superuser, which bypasses RLS; the default is now the application role.
DB_DSN = os.getenv("DATABASE_URL", "postgresql://app_user:apppassword@localhost:5433/postgres")
POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "5"))
POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "20"))

# Key that signs the tenant sent to the RLS policies (SEC-05). The same key lives in
# tenant_security.signing_key, unreadable for app_user. Without it no read is possible
# (the signature would not validate and RLS would hide everything), so the process does
# not start: better than a vague "no data" failure on every query.
TENANT_SIGNING_KEY = os.getenv("TENANT_SIGNING_KEY")
if not TENANT_SIGNING_KEY:
    raise RuntimeError(
        "TENANT_SIGNING_KEY is not set. Add it to your .env file "
        "(generate one with: openssl rand -hex 32) and seed the same key into the "
        "database with sql/migrations/apply_tenant_signing.sql."
    )
if len(TENANT_SIGNING_KEY) < 32:
    raise RuntimeError(
        "TENANT_SIGNING_KEY is too short (minimum 32 characters). "
        "Generate one with: openssl rand -hex 32"
    )
_SIGNING_KEY_BYTES = TENANT_SIGNING_KEY.encode()


def sign_tenant(tenant: str) -> str:
    """Signs the tenant in exactly the form app_current_tenant() verifies in SQL.

    pgcrypto computes hmac(text, key, 'sha256') over the bytes of both strings; this
    does the same and compares in hexadecimal.
    """
    return hmac.new(_SIGNING_KEY_BYTES, tenant.encode(), hashlib.sha256).hexdigest()

_pool: asyncpg.Pool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None
_pool_lock: asyncio.Lock | None = None


async def get_pool() -> asyncpg.Pool:
    """The process pool, created on the first call.

    It is created on demand and not at FastAPI startup because the ingestion CLI and the
    scripts use it too. An asyncpg pool belongs to the event loop that created it: if
    the loop changes (a script that calls asyncio.run several times), a new one is created.
    """
    global _pool, _pool_loop, _pool_lock
    loop = asyncio.get_running_loop()
    if _pool_loop is not loop:
        _pool, _pool_loop, _pool_lock = None, loop, asyncio.Lock()
    # Without the lock, the five searches launched by asyncio.gather would create five pools.
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
    """A pooled connection inside a transaction, with the tenant set for RLS.

    The tenant is set with set_config(..., true): it is local to the transaction and goes
    away with it, so a connection returned to the pool does not keep the tenant of
    whoever used it before. It travels as a parameter, never interpolated into the SQL (SEC-02).

    Its HMAC signature travels with the tenant (SEC-05). The RLS policies do not read
    app.current_tenant: they call app_current_tenant(), which returns the tenant only if
    the signature matches a key app_user cannot read. An injected statement can rewrite
    both variables, but cannot produce a valid signature, and then the function returns
    NULL and no row is visible. This is the only place in the code that sets the tenant.
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
