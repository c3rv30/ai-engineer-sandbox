"""Base PostgreSQL desechable para la capa de base de datos.

Cada ejecución levanta su propia base desde volumen vacío con docker-compose.yml y los
scripts de sql/, y la borra al terminar. Nunca toca la base de desarrollo: otro
proyecto Compose (`sandbox_tests`), otro puerto y otro volumen, que se borra por su
nombre exacto. Si la base no se puede levantar, la sesión falla: una capa de base de
datos saltada en silencio parecería superada sin haber comprobado nada.
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
    """Proyecto Compose al que pertenece un volumen, o None si no existe."""
    r = _run(["docker", "volume", "inspect", name])
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)[0].get("Labels", {}).get("com.docker.compose.project", "")


def _teardown(compose):
    _run([*compose, "down", "--remove-orphans"])
    owner = _volume_project(VOLUME)
    if owner is None:
        return
    # Solo por nombre exacto y solo si es de este proyecto: nunca prune ni prefijos.
    if owner != PROJECT:
        pytest.fail(f"El volumen {VOLUME} existe pero pertenece al proyecto {owner!r}; no se borra.", pytrace=False)
    r = _run(["docker", "volume", "rm", VOLUME])
    if r.returncode != 0:
        pytest.fail(f"No se pudo borrar el volumen {VOLUME}: {r.stderr.strip()}", pytrace=False)


@pytest.fixture(scope="session", autouse=True)
def test_database():
    # Guardián del DSN: src/services/db.py fija la base al importarse. Si algo lo importó
    # antes de que tests/conftest.py fijara el entorno, apuntaría a desarrollo.
    from src.services import db
    if f":{TEST_DB_PORT}/" not in db.DB_DSN or f":{DEV_DB_PORT}/" in db.DB_DSN:
        pytest.exit(f"src.services.db.DB_DSN no apunta a la base de pruebas: {db.DB_DSN}", returncode=1)

    with tempfile.TemporaryDirectory() as tmp:
        override = Path(tmp) / "override.yml"
        override.write_text(OVERRIDE)
        compose = ["docker", "compose", "-p", PROJECT, "--project-directory", str(REPO),
                   "-f", str(REPO / "docker-compose.yml"), "-f", str(override)]
        try:
            # Restos de una ejecución interrumpida (kill -9, Ctrl+C durante el arranque).
            _teardown(compose)
            up = _run([*compose, "up", "-d", "--wait", "--wait-timeout", "120"], timeout=240)
        except FileNotFoundError:
            pytest.fail("No se pudo levantar la base de pruebas: el comando 'docker' no está disponible.", pytrace=False)
        except subprocess.TimeoutExpired:
            _teardown(compose)
            pytest.fail("No se pudo levantar la base de pruebas: docker compose no respondió a tiempo.", pytrace=False)
        if up.returncode != 0:
            _teardown(compose)
            pytest.fail("No se pudo levantar la base de pruebas con docker compose:\n"
                        + (up.stderr or up.stdout).strip(), pytrace=False)
        try:
            yield
        finally:
            _teardown(compose)


@pytest.fixture(scope="session", autouse=True)
async def app_pool(test_database):
    """Cierra al final de la sesión el pool que la aplicación crea bajo demanda."""
    from src.services.db import close_pool
    yield
    await close_pool()


@pytest.fixture
async def superuser():
    """Conexión como postgres, que elude RLS: para sembrar y para inspeccionar."""
    conn = await asyncpg.connect(SUPERUSER_DSN)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def app_user_conn():
    """Conexión directa como app_user, sin tenant ni firma: lo que tendría una sentencia inyectada."""
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
    finally:
        await conn.close()
