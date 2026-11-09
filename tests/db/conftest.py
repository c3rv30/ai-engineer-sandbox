"""Disposable PostgreSQL database for the database layer.

Each run starts its own database from an empty volume with docker-compose.yml and the
sql/ scripts, and deletes it at the end. It never touches the development database:
another Compose project (`sandbox_tests`), another port and another volume, deleted by
its exact name. If the database cannot be started, the session fails: a database layer
skipped silently would look passed without having checked anything.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import asyncpg
import pytest

from tests.conftest import TEST_DB_PORT

REPO = Path(__file__).resolve().parents[2]
DB_DIR = Path(__file__).resolve().parent
PROJECT = "sandbox_tests"
VOLUME = f"{PROJECT}_pgdata"
SUPERUSER_DSN = f"postgresql://postgres:postgrespassword@127.0.0.1:{TEST_DB_PORT}/postgres"
DEV_DB_PORT = 5433

OVERRIDE = f"""services:
  postgres:
    ports: !override ["127.0.0.1:{TEST_DB_PORT}:5432"]
    restart: !reset null
"""


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.path.is_relative_to(DB_DIR):
            item.add_marker(pytest.mark.db)


def _run(cmd, timeout=180):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout)


def _volume_project(name):
    """Compose project a volume belongs to, or None if it does not exist."""
    r = _run(["docker", "volume", "inspect", name])
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)[0].get("Labels", {}).get("com.docker.compose.project", "")


def _teardown(compose):
    _run([*compose, "down", "--remove-orphans"])
    owner = _volume_project(VOLUME)
    if owner is None:
        return
    # Only by exact name and only if it belongs to this project: never prune or prefixes.
    if owner != PROJECT:
        pytest.fail(f"Volume {VOLUME} exists but belongs to project {owner!r}; not deleting it.", pytrace=False)
    r = _run(["docker", "volume", "rm", VOLUME])
    if r.returncode != 0:
        pytest.fail(f"Could not delete volume {VOLUME}: {r.stderr.strip()}", pytrace=False)


@pytest.fixture(scope="session", autouse=True)
def test_database():
    # DSN guard: src/services/db.py pins the database at import time. If something imported
    # it before tests/conftest.py set the environment, it would point at development.
    from src.services import db
    if f":{TEST_DB_PORT}/" not in db.DB_DSN or f":{DEV_DB_PORT}/" in db.DB_DSN:
        pytest.exit(f"src.services.db.DB_DSN does not point at the test database: {db.DB_DSN}", returncode=1)

    with tempfile.TemporaryDirectory() as tmp:
        override = Path(tmp) / "override.yml"
        override.write_text(OVERRIDE)
        compose = ["docker", "compose", "-p", PROJECT, "--project-directory", str(REPO),
                   "-f", str(REPO / "docker-compose.yml"), "-f", str(override)]
        try:
            # Leftovers of an interrupted run (kill -9, Ctrl+C during startup).
            _teardown(compose)
            up = _run([*compose, "up", "-d", "--wait", "--wait-timeout", "120"], timeout=240)
        except FileNotFoundError:
            pytest.fail("Could not start the test database: the 'docker' command is not available.", pytrace=False)
        except subprocess.TimeoutExpired:
            _teardown(compose)
            pytest.fail("Could not start the test database: docker compose did not respond in time.", pytrace=False)
        if up.returncode != 0:
            _teardown(compose)
            pytest.fail("Could not start the test database with docker compose:\n"
                        + (up.stderr or up.stdout).strip(), pytrace=False)
        try:
            yield
        finally:
            _teardown(compose)


@pytest.fixture(scope="session", autouse=True)
async def app_pool(test_database):
    """Closes, at the end of the session, the pool the application creates on demand."""
    from src.services.db import close_pool
    yield
    await close_pool()


@pytest.fixture
async def superuser():
    """Connection as postgres, which bypasses RLS: for seeding and inspecting."""
    conn = await asyncpg.connect(SUPERUSER_DSN)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def app_user_conn():
    """Direct connection as app_user, with no tenant or signature: what an injected statement would have."""
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
    finally:
        await conn.close()
