import os
import instructor
from pydantic import BaseModel, Field
from anthropic import AsyncAnthropic
from langfuse import observe

# Parchear el cliente de Anthropic con Instructor
client = instructor.from_anthropic(AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY")))

class QueryIntent(BaseModel):
    intent_type: str = Field(
        description="Debe ser 'casual_greeting', 'knowledge_search', 'tool_execution' o 'out_of_scope'."
    )
    search_queries: list[str] = Field(
        description="Si es 'knowledge_search', genera 3 variaciones de la pregunta optimizadas para búsqueda vectorial (BM25 y similitud). Si no, vacío.",
        default_factory=list
    )
    hypothetical_document: str = Field(
        description="Si es 'knowledge_search', redacta un párrafo hipotético de cómo se vería el documento ideal que responde a la pregunta (técnica HyDE). Si no, vacío.",
        default=""
    )
    direct_answer: str = Field(
        description="Si es 'casual_greeting' o 'out_of_scope', escribe tu respuesta final aquí. Si no, vacío.",
        default=""
    )
    tool_name: str = Field(
        description="Si es 'tool_execution', el nombre exacto de la herramienta a ejecutar: 'get_current_time', 'get_crypto_price', 'get_github_profile'.",
        default=""
    )
    tool_args: dict = Field(
        description="Si es 'tool_execution', diccionario JSON con los parámetros para la función (ej. {'symbol': 'bitcoin'} o {'username': 'torvalds'}).",
        default_factory=dict
    )

@observe(name="agentic_query_router")
async def analyze_query(query: str, history: list = None) -> QueryIntent:
    """
    Agente enrutador: Analiza la intención del usuario y resuelve correferencias usando el historial.
    """
    history_str = ""
    if history:
        # Formatear el historial reciente (últimos 4 mensajes para no inflar el token count)
        recent_history = history[-4:]
        lineas = []
        for msg in recent_history:
            # El historial lo envía el cliente: un turno sin 'role'/'content' no debe
            # tumbar la petición entera con un KeyError, simplemente se ignora.
            if not isinstance(msg, dict):
                continue
            role, content = msg.get("role"), msg.get("content")
            if role and content:
                lineas.append(f"- {role.upper()}: {content}")
        if lineas:
            history_str = "Historial reciente de la conversación:\n" + "\n".join(lineas) + "\n"
            
    prompt = f"""
    Eres el "Router" de un AI Engineer Sandbox que actualmente está analizando el currículum y perfil profesional del ingeniero Bryan Bobadilla.
    
    Tu tarea es analizar la siguiente entrada del usuario:
    "{query}"
    
    {history_str}
    
    Determina la intención de la entrada usando estas reglas:
    - `casual_greeting`: Si es un simple saludo (Hola, qué tal).
    - `knowledge_search`: Si es una pregunta sobre el currículum, la experiencia de Bryan Bobadilla, tecnologías, arquitectura de software, nube, o contexto técnico del proyecto.
    - `tool_execution`: Si el usuario pregunta algo que se pueda responder con las herramientas disponibles (Hora actual, Precio de Criptomonedas, o Perfiles de GitHub).
    - `out_of_scope`: ÚNICAMENTE si es una pregunta de política, religión u otros temas no relacionados y que NO se puedan responder con las herramientas.
    
    Herramientas disponibles (SOLO para 'tool_execution'):
    1. get_current_time: No requiere argumentos.
    2. get_crypto_price: Requiere argumento 'symbol' (ej. bitcoin, ethereum).
    3. get_github_profile: Requiere argumento 'username'.
    
    IMPORTANTE: Si la intención es 'knowledge_search':
    1. Genera 3 variaciones diferentes de la pregunta en `search_queries` para abarcar sinónimos y redacciones distintas (Multi-Query). Si la pregunta depende de historial (ej: "Y qué hizo ahí?"), resuelve la correferencia en todas las variaciones.
    2. Redacta un `hypothetical_document` de 2-3 oraciones fingiendo ser el fragmento de currículum o documentación ideal que respondería a la pregunta, usando terminología técnica exacta (HyDE).
    """
    
    # Usamos claude-haiku-4-5-20251001 que descubrimos que funciona perfecto en tu cuenta
    # Haiku es súper rápido y barato, ideal para ruteo
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
        response_model=QueryIntent,
    )
    
    return response
