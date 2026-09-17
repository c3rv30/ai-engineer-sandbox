"""Regresión del detalle de los errores internos (SEC-06).

Antes, el texto de la excepción llegaba literal al cliente: rutas del servidor y
mensajes del SDK de Anthropic. Ahora va al log, y al cliente solo un identificador.
"""
import logging
import re

import pytest

from tests.api.dobles import guion_redactor, guion_supervisor

RUTA_TEMPORAL = "/var/folders/v2/n7jcjy_11cscqrgkctpn931c0000gn/T/tmp_f3a0h9w.pdf"
MENSAJE_PROVEEDOR = "Error code: 401 - {'type': 'error', 'message': 'API key is invalid.'}"
GENERICO = re.compile(r"^Error interno \(([0-9a-f]{8})\)$")


def identificador(texto):
    coincidencia = GENERICO.match(texto)
    assert coincidencia, f"mensaje inesperado para el cliente: {texto!r}"
    return coincidencia.group(1)


def test_fallo_interno_en_respuesta_normal(api, caplog):
    api.guion(guion_redactor("no llega"))
    api.falla_con(RuntimeError(f"Failed to open file '{RUTA_TEMPORAL}' as type pdf"))
    with caplog.at_level(logging.ERROR):
        r = api.client.post("/chat/", json={"query": "¿Dónde trabajó?"}, headers=api.cabecera())

    assert r.status_code == 500
    detalle = r.json()["detail"]
    ident = identificador(detalle)
    assert RUTA_TEMPORAL not in r.text and "Failed to open" not in r.text
    assert caplog.text.count(ident) == 1
    assert RUTA_TEMPORAL in caplog.text and "Traceback" in caplog.text


def test_fallo_interno_durante_el_stream(api, caplog):
    api.guion(guion_redactor("no llega"))
    # Falla después de la primera emisión: el cliente ya recibió progreso.
    api.falla_con(RuntimeError(MENSAJE_PROVEEDOR), tras=1)
    with caplog.at_level(logging.ERROR):
        r = api.client.post("/chat/stream/", json={"query": "¿Dónde trabajó?"}, headers=api.cabecera())

    eventos = api.eventos(r)
    assert r.status_code == 200  # el stream ya había empezado
    assert "error" in eventos[-1], eventos
    ident = identificador(eventos[-1]["error"])
    assert "API key is invalid" not in r.text and "401" not in r.text
    assert caplog.text.count(ident) == 1
    assert "API key is invalid" in caplog.text


def test_fallo_interno_en_la_ingesta(api, caplog, monkeypatch):
    async def ingesta_rota(*args, **kwargs):
        raise RuntimeError(f"Failed to open file '{RUTA_TEMPORAL}' as type pdf")

    monkeypatch.setattr(api._ingest, "ingest_file", ingesta_rota)
    with caplog.at_level(logging.ERROR):
        r = api.client.post("/ingest/", files={"file": ("cv.pdf", b"%PDF-1.4 roto", "application/pdf")},
                            headers=api.cabecera())

    assert r.status_code == 500
    ident = identificador(r.json()["detail"])
    assert RUTA_TEMPORAL not in r.text
    assert caplog.text.count(ident) == 1
    assert RUTA_TEMPORAL in caplog.text


# --- Lo que no debe convertirse en el mensaje genérico ---

def test_extension_no_permitida_conserva_su_mensaje(api):
    r = api.client.post("/ingest/", files={"file": ("malo.exe", b"MZ", "application/octet-stream")},
                        headers=api.cabecera())
    assert r.status_code == 400
    assert "Extensión no permitida" in r.json()["detail"]
    assert not GENERICO.match(r.json()["detail"])
    assert api.registro.ingestas == []


def test_grafo_sin_respuesta_final_conserva_su_mensaje(api):
    guion = guion_supervisor("da igual")
    guion.estado_final = {"intent_type": "knowledge_search", "final_answer": None, "documents": []}
    api.guion(guion)
    r = api.client.post("/chat/", json={"query": "¿Dónde trabajó?"}, headers=api.cabecera())
    assert r.status_code == 500
    assert r.json()["detail"] == "El Grafo de Agentes no devolvió una respuesta final."


@pytest.mark.parametrize("cuerpo", [{"query": "x", "top_k_rerank": 0}, {"query": "x", "top_k_retrieve": 99}])
def test_validacion_del_contrato_sigue_siendo_422(api, cuerpo):
    r = api.client.post("/chat/", json=cuerpo, headers=api.cabecera())
    assert r.status_code == 422
