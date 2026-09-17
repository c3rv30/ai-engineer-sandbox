"""Regresión de la respuesta del stream en todos los caminos (BUG-09).

Cuando el supervisor resuelve la petición por sí mismo —saludo, tema fuera de alcance
o herramienta—, el grafo termina sin pasar por el redactor, así que nadie emite el
texto por el canal 'custom'. El cliente se quedaba con la línea de progreso y nada más.
"""
import pytest

from tests.api.dobles import PROGRESO_SUPERVISOR, guion_redactor, guion_supervisor

CASOS = [
    ("casual_greeting", "¡Hola! Soy el asistente del sandbox, ¿en qué te ayudo?"),
    ("out_of_scope", "Esa pregunta queda fuera de lo que puedo responder."),
    ("tool_execution", "¡Herramienta ejecutada (get_crypto_price)! Resultado:\n\nBTC: 64.200 USD"),
]


def stream(api, query="hola", **cuerpo):
    return api.client.post("/chat/stream/", json={"query": query, **cuerpo}, headers=api.cabecera())


@pytest.mark.parametrize("intent, texto", CASOS)
def test_el_supervisor_resuelve_y_el_stream_devuelve_la_respuesta(api, intent, texto):
    api.guion(guion_supervisor(texto, intent_type=intent))
    eventos = api.eventos(stream(api))

    final = eventos[-1]
    assert texto in final["answer"], final
    assert final["answer"] != PROGRESO_SUPERVISOR  # el defecto: solo progreso
    assert "confidence_score" in final and "requires_more_info" in final


@pytest.mark.parametrize("intent, texto", CASOS)
def test_la_respuesta_del_supervisor_no_se_duplica(api, intent, texto):
    api.guion(guion_supervisor(texto, intent_type=intent))
    eventos = api.eventos(stream(api))
    assert eventos[-1]["answer"].count(texto) == 1


def test_el_redactor_emite_su_texto_una_sola_vez(api):
    texto = "Trabajó en Betterfly desde abril de 2024."
    api.guion(guion_redactor(texto, trozos=["Trabajó en Betterfly ", "desde abril de 2024."]))
    eventos = api.eventos(stream(api, query="¿Dónde trabajó?"))

    final = eventos[-1]
    assert final["answer"].count(texto) == 1, final["answer"]
    # El texto llegó en trozos: hay más eventos que en el camino del supervisor.
    assert len(eventos) > 4


def test_el_texto_del_stream_solo_crece(api):
    # El frontend renderiza diferencias de caracteres: un evento más corto que el
    # anterior le haría perder texto.
    api.guion(guion_redactor("Una respuesta larga y detallada.", trozos=["Una respuesta ", "larga y ", "detallada."]))
    answers = [e["answer"] for e in api.eventos(stream(api, query="¿Dónde trabajó?")) if "answer" in e]
    assert answers == sorted(answers, key=len)
    assert all(b.startswith(a) for a, b in zip(answers, answers[1:]))


def test_acierto_de_cache_devuelve_un_solo_evento_sin_ejecutar_el_grafo(api):
    api.cache_devuelve({"answer": "Respuesta guardada.", "sources": [], "confidence_score": 0.9,
                        "requires_more_info": False})
    eventos = api.eventos(stream(api, query="¿Dónde trabajó?"))

    assert len(eventos) == 1
    assert eventos[0]["answer"] == "⚡ [CACHE HIT] Respuesta guardada."
    assert api.grafo.invocaciones == []
    assert api.registro.cache_escrituras == []
