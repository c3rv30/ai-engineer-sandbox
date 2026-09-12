import os
from typing import List, Dict, Optional
import instructor
from anthropic import AsyncAnthropic
from langfuse import observe

from src.models.search import RerankedResult
from src.models.structured import StructuredAnswer
from src.services.history import format_history

# Inicializar cliente Anthropic y envolverlo con instructor
anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
client = instructor.from_anthropic(anthropic_client)

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
    """
    
    # Preparar el contexto en texto plano
    context_text = ""
    for idx, c in enumerate(context, 1):
        context_text += f"\n--- Documento {idx} (ID: {c.id}) ---\n{c.content}\n"

    history_str = format_history(history)

    prompt = f"""
    Eres un asistente experto de AI Engineering. Tu objetivo es responder a la pregunta del usuario utilizando ÚNICAMENTE la información provista en el Contexto.
    Si la información no es suficiente, debes indicarlo en 'requires_more_info'.
    Cita las fuentes usando el ID del documento.
    
    {user_profile}
    
    {history_str}
    Pregunta: {query}
    
    IMPORTANTE: Si la pregunta depende del historial (ej: "¿Y en qué años?"), resuelve primero a qué se refiere usando el turno anterior y responde ÚNICAMENTE sobre ese referente. El Contexto puede traer documentos de más: no lo vuelques entero, responde solo lo que se te preguntó.
    
    Contexto:
    {context_text}
    """

    # Ejecutar la llamada con instructor
    # Claude 3.5 Haiku o Sonnet son ideales para esto.
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[
            {"role": "user", "content": prompt}
        ],
        response_model=StructuredAnswer
    )
    
    return response

from instructor import Partial
from typing import AsyncGenerator

@observe(name="generate_structured_answer_stream")
async def generate_answer_stream(query: str, context: List[RerankedResult], user_profile: str = "") -> AsyncGenerator[str, None]:
    """
    Streaming response usando Partial.
    """
    context_text = ""
    for idx, c in enumerate(context, 1):
        context_text += f"\n--- Documento {idx} (ID: {c.id}) ---\n{c.content}\n"

    prompt = f"""
    Eres un asistente experto de AI Engineering. Tu objetivo es responder a la pregunta del usuario utilizando ÚNICAMENTE la información provista en el Contexto.
    
    MUY IMPORTANTE: Debes devolver tu respuesta estructurada. Si vas a escribir un análisis largo, pon todo el texto formateado en Markdown dentro del campo 'answer'. No respondas con texto plano fuera del esquema JSON.
    
    {user_profile}
    
    Pregunta: {query}
    Contexto: {context_text}
    """

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8192, # Máximo permitido para análisis largos
            messages=[{"role": "user", "content": prompt}],
            response_model=Partial[StructuredAnswer],
            stream=True
        )
        
        async for partial_model in response:
            # Emitimos un JSON string de lo que llevamos generado
            yield partial_model.model_dump_json() + "\n"
    except Exception as e:
        # En caso de que Claude falle en generar el JSON, emitimos el error como json
        import json
        yield json.dumps({"error": f"Error de generación: {str(e)}"}) + "\n"
