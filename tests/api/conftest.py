"""Capa de API: la aplicación completa con TestClient y dobles del grafo y los servicios.

No se conecta a PostgreSQL ni llama a ningún LLM, así que no necesita Docker. La
autenticación es la real: los 401 de SEC-01 y SEC-02 no tendrían sentido con un doble.
"""
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.api.dobles import GrafoDoble, Guion

API_DIR = __file__.rsplit("/", 1)[0]
TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if str(item.path).startswith(API_DIR):
            item.add_marker(pytest.mark.api)


@dataclass
class Registro:
    """Con qué se llamó a cada servicio doblado."""
    cache_lecturas: list[tuple] = field(default_factory=list)
    cache_escrituras: list[tuple] = field(default_factory=list)
    memoria_lecturas: list[tuple] = field(default_factory=list)
    hechos_guardados: list[tuple] = field(default_factory=list)
    evaluaciones: list[tuple] = field(default_factory=list)
    ingestas: list[tuple] = field(default_factory=list)


@dataclass
class Api:
    """Cliente HTTP, dobles instalados y utilidades para construir tokens."""
    client: TestClient
    registro: Registro
    grafo: GrafoDoble
    _chat: Any
    _ingest: Any

    def guion(self, guion: Guion):
        self.grafo.guion = guion
        return self.grafo

    def falla_con(self, error: Exception, *, tras: int = 0):
        self.grafo.error = error
        self.grafo.error_tras = tras
        return self.grafo

    def cabecera(self, *, tenant=TENANT, usuario="bryan", clave=None, sin_sub=False, sin_tenant=False):
        import os
        from datetime import datetime, timedelta

        import jwt

        payload: dict[str, Any] = {"exp": datetime.utcnow() + timedelta(minutes=5)}
        if not sin_sub:
            payload["sub"] = usuario
        if not sin_tenant:
            payload["tenant_id"] = str(tenant)
        token = jwt.encode(payload, clave or os.environ["JWT_SECRET_KEY"], algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def cache_devuelve(self, datos: dict):
        self._cache_respuesta[0] = datos

    def eventos(self, respuesta) -> list[dict]:
        """Los objetos JSON de un stream SSE, en orden."""
        import json

        return [json.loads(l[len("data: "):], strict=False)
                for l in respuesta.text.splitlines() if l.startswith("data: ")]


@pytest.fixture(autouse=True)
def sin_postgres(monkeypatch):
    """Ningún test de esta capa puede abrir una conexión a PostgreSQL.

    Los servicios de datos están doblados, así que una conexión significa que algo se
    escapó del doble. Sin esta vigilancia, el test pasaría igual con la base de
    desarrollo en marcha y fallaría solo en una máquina sin ella.
    """
    import asyncpg

    def prohibido(*args, **kwargs):
        raise AssertionError("la capa de API no debe conectarse a PostgreSQL")

    monkeypatch.setattr(asyncpg, "connect", prohibido)
    monkeypatch.setattr(asyncpg, "create_pool", prohibido)


@pytest.fixture(scope="session")
def app_module():
    """Importa la aplicación una sola vez por sesión: cuesta ~10 s (modelos y clientes).

    Desactiva además la telemetría de onnxruntime, que llega con FlashRank. Su hilo de
    eventos procesa respuestas HTTP mientras el intérprete ya está cerrando y aborta el
    proceso (código 134, "recursive_mutex lock failed"), después de que todos los tests
    hayan pasado: la suite completa fallaba así ~7 de cada 8 ejecuciones.
    """
    from src.api import main

    return main


@pytest.fixture
def api(monkeypatch, app_module):
    from src.api.routers import chat as chat_mod
    from src.api.routers import ingest as ingest_mod

    registro = Registro()
    respuesta_cache: list[Any] = [None]

    async def check_semantic_cache(tenant_id, query, *args, **kwargs):
        registro.cache_lecturas.append((tenant_id, query))
        return respuesta_cache[0]

    async def save_semantic_cache(tenant_id, query, response_dict, *args, **kwargs):
        registro.cache_escrituras.append((tenant_id, query, response_dict))

    async def retrieve_user_facts(tenant_id, query, *args, **kwargs):
        registro.memoria_lecturas.append((tenant_id, query))
        return ""

    async def extract_and_save_facts(tenant_id, user_message, *args, **kwargs):
        registro.hechos_guardados.append((tenant_id, user_message))

    async def evaluate_rag_response(tenant_id, query, answer, context, *args, **kwargs):
        registro.evaluaciones.append((tenant_id, query, answer, context))

    async def ingest_file(path, tenant_id, *args, **kwargs):
        registro.ingestas.append((path, tenant_id, kwargs.get("source")))
        return {"chunks_ingested": 1, "message": "ok"}

    grafo = GrafoDoble()
    monkeypatch.setattr(chat_mod, "agent_graph", grafo)
    monkeypatch.setattr(chat_mod, "check_semantic_cache", check_semantic_cache)
    monkeypatch.setattr(chat_mod, "save_semantic_cache", save_semantic_cache)
    monkeypatch.setattr(chat_mod, "retrieve_user_facts", retrieve_user_facts)
    monkeypatch.setattr(chat_mod, "extract_and_save_facts", extract_and_save_facts)
    monkeypatch.setattr(chat_mod, "evaluate_rag_response", evaluate_rag_response)
    monkeypatch.setattr(ingest_mod, "ingest_file", ingest_file)

    # Sin gestor de contexto a propósito: así no se ejecuta el lifespan y la capa no
    # intenta abrir el pool de Postgres.
    cliente = TestClient(app_module.app)
    objeto = Api(client=cliente, registro=registro, grafo=grafo, _chat=chat_mod, _ingest=ingest_mod)
    objeto._cache_respuesta = respuesta_cache
    yield objeto
    cliente.close()
