"""Regresión del objeto que se persiste en el caché (BUG-01).

El generador SSE acumula los mensajes de progreso de cada nodo en el texto que ve el
cliente. Ese texto no debe acabar en el caché ni en el evaluador: lo que se persiste
es la respuesta estructurada limpia.
"""
from tests.api.dobles import (
    PROGRESO_INVESTIGADOR, PROGRESO_SUPERVISOR, PREFIJO_REDACTOR, documento, guion_redactor,
)

TEXTO = "Trabajó en Betterfly desde abril de 2024."
PROGRESO = [PROGRESO_SUPERVISOR.strip(), PROGRESO_INVESTIGADOR.strip(), PREFIJO_REDACTOR.strip()]


def stream(api, **cuerpo):
    peticion = {"query": "¿Dónde trabajó?", **cuerpo}
    return api.client.post("/chat/stream/", json=peticion, headers=api.cabecera())


def test_lo_que_se_guarda_no_lleva_los_mensajes_de_progreso(api):
    api.guion(guion_redactor(TEXTO, trozos=["Trabajó en Betterfly ", "desde abril de 2024."]))
    r = stream(api)
    eventos = api.eventos(r)

    # Lo que ve el cliente sí lleva el progreso: es lo que renderiza la interfaz.
    emitido = eventos[-1]["answer"]
    assert all(marca in emitido for marca in PROGRESO), emitido
    assert TEXTO in emitido

    # Lo que se manda a persistir, no.
    assert len(api.registro.cache_escrituras) == 1
    guardado = api.registro.cache_escrituras[0][2]
    assert guardado["answer"] == TEXTO
    for marca in PROGRESO:
        assert marca not in guardado["answer"]
    assert guardado["confidence_score"] == 0.9 and guardado["requires_more_info"] is False


def test_el_evaluador_recibe_la_respuesta_limpia(api):
    docs = [documento("Betterfly, 2024", id_="doc-9")]
    api.guion(guion_redactor(TEXTO, documentos=docs))
    stream(api)

    assert len(api.registro.evaluaciones) == 1
    _, consulta, respuesta_evaluada, contexto = api.registro.evaluaciones[0]
    assert consulta == "¿Dónde trabajó?"
    assert respuesta_evaluada == TEXTO
    for marca in PROGRESO:
        assert marca not in respuesta_evaluada
    assert [d.id for d in contexto] == ["doc-9"]


def test_la_memoria_recibe_la_pregunta_del_usuario(api):
    api.guion(guion_redactor(TEXTO))
    stream(api)
    assert api.registro.hechos_guardados == [(api.grafo.invocaciones[0]["tenant_id"], "¿Dónde trabajó?")]


def test_respuesta_no_cacheable_no_se_guarda(api):
    # requires_more_info=True: el propio sistema la da por insuficiente (BUG-02).
    api.guion(guion_redactor(TEXTO, requiere_mas=True))
    stream(api)
    assert api.registro.cache_escrituras == []


def test_peticion_con_historial_ni_lee_ni_escribe_cache(api):
    api.guion(guion_redactor(TEXTO))
    stream(api, history=[{"role": "user", "content": "¿Trabajó en Betterfly?"},
                         {"role": "assistant", "content": "Sí."}])
    assert api.registro.cache_lecturas == []
    assert api.registro.cache_escrituras == []


def test_respuesta_normal_tambien_persiste_el_objeto_limpio(api):
    api.guion(guion_redactor(TEXTO))
    r = api.client.post("/chat/", json={"query": "¿Dónde trabajó?"}, headers=api.cabecera())
    assert r.status_code == 200
    assert r.json()["answer"] == TEXTO
    assert api.registro.cache_escrituras[0][2]["answer"] == TEXTO
