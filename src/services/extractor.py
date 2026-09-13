import os
from typing import AsyncGenerator, Dict, List, Optional
import instructor
from anthropic import AsyncAnthropic
from instructor import Partial
from langfuse import observe

from src.models.search import RerankedResult
from src.models.structured import StructuredAnswer
from src.services.history import format_history

# Inicializar cliente Anthropic y envolverlo con instructor
anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
client = instructor.from_anthropic(anthropic_client)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 8192


def _build_prompt(
    query: str,
    context: List[RerankedResult],
    user_profile: str = "",
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Construye el prompt del redactor.

    Lo comparten la versión completa y la de streaming a propósito: tener dos
    copias del prompt fue justamente la causa de que la instrucción anti-texto-plano
    (documentada en TROUBLESHOOTING.md §6) viviera solo en una de las dos.
    """
    context_text = ""
    for idx, c in enumerate(context, 1):
        context_text += f"\n--- Documento {idx} (ID: {c.id}) ---\n{c.content}\n"

    history_str = format_history(history)

    return f"""
    Eres un asistente experto de AI Engineering. Tu objetivo es responder a la pregunta del usuario utilizando ÚNICAMENTE la información provista en el Contexto.
    Si la información no es suficiente, debes indicarlo en 'requires_more_info'.
    Cita las fuentes usando el ID del documento.

    MUY IMPORTANTE: Debes devolver tu respuesta estructurada. Si vas a escribir un análisis largo, pon todo el texto formateado en Markdown dentro del campo 'answer'. No respondas con texto plano fuera del esquema JSON.

    {user_profile}

    {history_str}
    Pregunta: {query}

    IMPORTANTE: Si la pregunta depende del historial (ej: "¿Y en qué años?"), resuelve primero a qué se refiere usando el turno anterior y responde ÚNICAMENTE sobre ese referente. El Contexto puede traer documentos de más: no lo vuelques entero, responde solo lo que se te preguntó.

    Contexto:
    {context_text}
    """


@observe(name="generate_structured_answer")
async def generate_answer(
    query: str,
    context: List[RerankedResult],
    user_profile: str = "",
    history: Optional[List[Dict[str, str]]] = None,
) -> StructuredAnswer:
    """
    Toma la pregunta y el contexto recuperado, e invoca a Anthropic (Claude)
    para generar una respuesta estructurada validada con Pydantic.

    Recibe también el historial: sin él, una pregunta de seguimiento como
    "¿Y en qué años?" no tiene referente, y el redactor responde volcando todo
    el contexto recuperado en lugar de acotarse a lo que se le preguntó.

    El camino normal es `generate_answer_stream`; esta versión queda como
    repliegue cuando el streaming no logra completar el objeto estructurado.
    """
    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "user", "content": _build_prompt(query, context, user_profile, history)}
        ],
        response_model=StructuredAnswer
    )

    return response


@observe(name="generate_structured_answer_stream")
async def generate_answer_stream(
    query: str,
    context: List[RerankedResult],
    user_profile: str = "",
    history: Optional[List[Dict[str, str]]] = None,
) -> AsyncGenerator[Partial[StructuredAnswer], None]:
    """
    Igual que `generate_answer`, pero emitiendo el objeto según se construye.

    Emite el modelo parcial, no su JSON serializado, porque quien consume
    necesita tanto el texto incremental (para el SSE) como el objeto final
    (para el estado del grafo). Los primeros parciales llegan con `answer` a
    None: el modelo aún no ha abierto ese campo.
    """
    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "user", "content": _build_prompt(query, context, user_profile, history)}
        ],
        response_model=Partial[StructuredAnswer],
        stream=True
    )

    async for partial_model in response:
        yield partial_model
