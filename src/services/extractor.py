import os
from typing import List
import instructor
from anthropic import AsyncAnthropic
from langfuse import observe

from src.models.search import RerankedResult
from src.models.structured import StructuredAnswer

# Inicializar cliente Anthropic y envolverlo con instructor
anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
client = instructor.from_anthropic(anthropic_client)

@observe(name="generate_structured_answer")
async def generate_answer(query: str, context: List[RerankedResult], user_profile: str = "") -> StructuredAnswer:
    """
    Toma la pregunta y el contexto recuperado, e invoca a Anthropic (Claude)
    para generar una respuesta estructurada validada con Pydantic.
    """
    
    # Preparar el contexto en texto plano
    context_text = ""
    for idx, c in enumerate(context, 1):
        context_text += f"\n--- Documento {idx} (ID: {c.id}) ---\n{c.content}\n"

    prompt = f"""
    Eres un asistente experto de AI Engineering. Tu objetivo es responder a la pregunta del usuario utilizando ÚNICAMENTE la información provista en el Contexto.
    Si la información no es suficiente, debes indicarlo en 'requires_more_info'.
    Cita las fuentes usando el ID del documento.
    
    {user_profile}
    
    Pregunta: {query}
    
    Contexto:
    {context_text}
    """

    # Ejecutar la llamada con instructor
    # Claude 3.5 Haiku o Sonnet son ideales para esto.
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
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
            max_tokens=2048, # Aumentamos tokens para análisis largos
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
