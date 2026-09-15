import os
import uuid
import instructor
from pydantic import BaseModel, Field
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from src.services.db import tenant_connection
from src.services.embeddings import embed, to_pgvector

load_dotenv()

client = instructor.from_anthropic(AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY")))

class ExtractedFacts(BaseModel):
    new_facts: list[str] = Field(
        description="Lista de nuevos hechos, preferencias o información personal persistente sobre el usuario (máx. 3). Vacío si no hay nueva información relevante a largo plazo.",
        default_factory=list
    )

async def extract_and_save_facts(tenant_id: uuid.UUID, user_message: str):
    """
    Se ejecuta en background. Analiza si el usuario reveló nueva información sobre sí mismo.
    Si es así, la vectoriza y la guarda.
    """
    prompt = f"""
    Eres un extractor de memoria a largo plazo. Analiza el siguiente mensaje del usuario y determina si reveló algún hecho importante sobre sí mismo, sus preferencias, su stack tecnológico o su empresa.
    Solo extrae hechos que sean útiles para recordar en futuras sesiones. Escríbelos en tercera persona de forma concisa. (ej. "El usuario prefiere programar en Python", "El usuario trabaja en la empresa X").
    
    Mensaje del usuario: "{user_message}"
    """
    
    try:
        extraction: ExtractedFacts = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
            response_model=ExtractedFacts,
        )
        
        if not extraction.new_facts:
            return
            
        print(f"🧠 [Memory] Nuevos hechos detectados: {extraction.new_facts}")
        
        # Los embeddings se calculan antes de tomar conexión: es trabajo de CPU y
        # retendría una conexión del pool sin usarla.
        embeddings = [await embed(fact) for fact in extraction.new_facts]
        async with tenant_connection(tenant_id) as conn:
            
            for fact, fact_embedding in zip(extraction.new_facts, embeddings):
                emb_str = to_pgvector(fact_embedding)
                
                sql = """
                INSERT INTO user_memory (tenant_id, fact, fact_embedding)
                VALUES ($1, $2, $3::vector)
                """
                await conn.execute(sql, tenant_id, fact, emb_str)
    except Exception as e:
        print(f"Error extrayendo memoria: {e}")

async def retrieve_user_facts(tenant_id: uuid.UUID, query: str, top_k: int = 3) -> str:
    """
    Busca los hechos más relevantes del usuario basados en su pregunta actual.
    """
    # El embedding se calcula antes de tomar conexión: es trabajo de CPU y retendría
    # una conexión del pool sin usarla.
    emb_str = to_pgvector(await embed(query))
    async with tenant_connection(tenant_id) as conn:
        
        
        sql = """
        SELECT fact, 1 - (fact_embedding <=> $1::vector) AS similarity
        FROM user_memory
        ORDER BY fact_embedding <=> $1::vector
        LIMIT $2
        """
        rows = await conn.fetch(sql, emb_str, top_k)
        
        if not rows:
            return ""
            
        # Filtramos hechos con una similitud mínima para no traer basura
        relevant_facts = [row['fact'] for row in rows if row['similarity'] > 0.3]
        
        if not relevant_facts:
            return ""
            
        facts_str = "\n".join(f"- {f}" for f in relevant_facts)
        return f"<USER_PROFILE>\nInformación histórica conocida sobre el usuario:\n{facts_str}\n</USER_PROFILE>\n\n"
