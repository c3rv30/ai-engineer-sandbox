"""La capa no toca PostgreSQL: los servicios de datos están doblados."""
import asyncio

import asyncpg
import pytest

from tests.api.dobles import guion_redactor


def test_la_vigilancia_de_conexiones_esta_activa(api):
    # Control de la propia vigilancia: si un test intentara conectar, fallaría aquí.
    with pytest.raises(AssertionError, match="no debe conectarse"):
        asyncio.run(asyncpg.connect("postgresql://app_user:apppassword@127.0.0.1:5439/postgres"))
    with pytest.raises(AssertionError, match="no debe conectarse"):
        asyncio.run(asyncpg.create_pool("postgresql://app_user:apppassword@127.0.0.1:5439/postgres"))


def test_una_peticion_completa_no_abre_conexiones(api):
    api.guion(guion_redactor("Respuesta sin base de datos."))
    r = api.client.post("/chat/", json={"query": "¿Dónde trabajó?"}, headers=api.cabecera())
    assert r.status_code == 200
    # Los servicios doblados registraron las llamadas que habrían ido a Postgres.
    assert api.registro.cache_lecturas and api.registro.memoria_lecturas
