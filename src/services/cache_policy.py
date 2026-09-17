"""Política del caché semántico: qué peticiones lo usan y qué respuestas se guardan.

Vive fuera de src/api/routers/chat.py para poder comprobarla sin importar el grafo, los
modelos ni los clientes de Anthropic (BUG-07). Solo depende de src.models.
"""
from src.models.requests import ChatRequest, DEFAULT_TOP_K_RETRIEVE, DEFAULT_TOP_K_RERANK

# Solo se cachean respuestas que sigan valiendo la próxima vez que alguien pregunte
# algo parecido. El caché se consulta antes que el supervisor y compara por similitud,
# así que una herramienta cacheada devolvería datos viejos o de otra consulta (el
# precio de bitcoin a quien pregunta por ethereum), y un 'out_of_scope' contestaría a
# otra pregunta. Es una lista blanca porque intent_type lo escribe el LLM como texto
# libre: un valor inesperado no debe acabar en caché.
CACHEABLE_INTENTS = {"knowledge_search", "casual_greeting"}
MIN_CACHE_CONFIDENCE = 0.5


def is_cacheable(intent_type: str | None, answer: dict) -> bool:
    # Tampoco se fija para siempre una respuesta que el propio sistema da por insuficiente.
    return (intent_type in CACHEABLE_INTENTS
            and not answer.get("requires_more_info")
            and (answer.get("confidence_score") or 0) >= MIN_CACHE_CONFIDENCE)


def uses_default_retrieval(request: ChatRequest) -> bool:
    # El caché se indexa solo por la pregunta. Una respuesta obtenida con otros top_k no
    # es intercambiable con la de los valores por defecto, así que esas peticiones ni
    # leen ni escriben caché.
    return (request.top_k_retrieve == DEFAULT_TOP_K_RETRIEVE
            and request.top_k_rerank == DEFAULT_TOP_K_RERANK)


def is_cache_eligible(request: ChatRequest) -> bool:
    """Si esta petición puede leer o escribir caché.

    El caché se indexa solo por el texto de la pregunta, y desde BUG-03 la respuesta
    depende también del historial: "¿Y en qué años fue eso?" significa cosas distintas
    según el turno anterior. Dos conversaciones que terminan en el mismo seguimiento
    tienen similitud 1,0 y comparten entrada (BUG-10). Reproducido contra la API real:
    un seguimiento sobre Itaú/Kabeli recibía los años de MisterGas, presentados como
    "Según el historial anterior" —un historial que no era el del usuario—.

    Así que una petición con historial ni lee ni escribe caché, igual que una con
    top_k propios. La alternativa —indexar por la consulta que ya resolvió el
    supervisor— conservaría el caché en los seguimientos, pero solo cierra el defecto
    si el supervisor incrusta siempre el referente completo, y obliga a consultar el
    caché después de él, pagando su llamada al LLM también en los aciertos.
    """
    return uses_default_retrieval(request) and not request.history
