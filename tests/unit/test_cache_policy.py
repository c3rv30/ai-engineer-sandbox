"""Regresión de la política del caché semántico (BUG-02, BUG-06, BUG-10).

El caché se consulta antes que el supervisor y compara solo por similitud del texto de
la pregunta, así que únicamente puede guardar respuestas que valgan para cualquier
petición parecida.
"""
import pytest
from pydantic import ValidationError

from src.services.cache_policy import is_cacheable, is_cache_eligible, uses_default_retrieval
from src.models.requests import ChatRequest

BUENA = {"requires_more_info": False, "confidence_score": 0.9}


# --- BUG-02: qué respuestas se pueden guardar ---

@pytest.mark.parametrize("intent", ["tool_execution", "out_of_scope", "algo_inventado", None, ""])
def test_intencion_no_cacheable(intent):
    # Una herramienta cacheada devolvía el precio de bitcoin a quien preguntaba por ethereum.
    assert not is_cacheable(intent, BUENA)


@pytest.mark.parametrize("intent", ["knowledge_search", "casual_greeting"])
def test_respuesta_reutilizable(intent):
    assert is_cacheable(intent, BUENA)


def test_respuesta_que_pide_mas_informacion():
    assert not is_cacheable("knowledge_search", {"requires_more_info": True, "confidence_score": 0.9})


@pytest.mark.parametrize("confianza", [0.49, 0.0, None])
def test_confianza_insuficiente_o_ausente(confianza):
    assert not is_cacheable("knowledge_search", {"requires_more_info": False, "confidence_score": confianza})


def test_confianza_sin_campo():
    assert not is_cacheable("knowledge_search", {"requires_more_info": False})


def test_confianza_en_el_umbral():
    assert is_cacheable("knowledge_search", {"requires_more_info": False, "confidence_score": 0.5})


# --- BUG-06: parámetros de recuperación propios ---

def test_parametros_por_defecto_usan_cache():
    request = ChatRequest(query="¿Dónde trabajó?")
    assert (request.top_k_retrieve, request.top_k_rerank) == (15, 10)
    assert uses_default_retrieval(request)
    assert is_cache_eligible(request)


@pytest.mark.parametrize("campos", [{"top_k_retrieve": 14}, {"top_k_rerank": 3}, {"top_k_retrieve": 50, "top_k_rerank": 20}])
def test_parametros_propios_no_usan_cache(campos):
    request = ChatRequest(query="¿Dónde trabajó?", **campos)
    assert not uses_default_retrieval(request)
    assert not is_cache_eligible(request)


@pytest.mark.parametrize("campos", [
    {"top_k_retrieve": 0}, {"top_k_retrieve": -1}, {"top_k_retrieve": 51},
    {"top_k_rerank": 0}, {"top_k_rerank": 21},
])
def test_parametros_fuera_de_rango(campos):
    with pytest.raises(ValidationError):
        ChatRequest(query="¿Dónde trabajó?", **campos)


@pytest.mark.parametrize("campos", [{"top_k_retrieve": 1, "top_k_rerank": 1}, {"top_k_retrieve": 50, "top_k_rerank": 20}])
def test_parametros_en_los_limites(campos):
    ChatRequest(query="¿Dónde trabajó?", **campos)


# --- BUG-10: historial ---

def test_peticion_con_historial_no_usa_cache():
    # Dos conversaciones que terminan en "¿Y en qué años fue eso?" compartían entrada.
    request = ChatRequest(
        query="¿Y en qué años fue eso?",
        history=[{"role": "user", "content": "¿Trabajó en Itaú?"}, {"role": "assistant", "content": "Sí."}],
    )
    assert uses_default_retrieval(request)
    assert not is_cache_eligible(request)
