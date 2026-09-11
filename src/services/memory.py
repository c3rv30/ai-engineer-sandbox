import os
import uuid
import asyncio
import asyncpg
import instructor
from pydantic import BaseModel, Field
from anthropic import AsyncAnthropic
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()
DB_DSN = os.getenv("DATABASE_URL", "postgresql://app_user:apppassword@localhost:5433/postgres")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
model = SentenceTransformer(EMBEDDING_MODEL)

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
        
        conn = await asyncpg.connect(DB_DSN)
        try:
            await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
            
            for fact in extraction.new_facts:
                fact_embedding = await asyncio.to_thread(model.encode, fact)
                emb_str = f"[{','.join(str(x) for x in fact_embedding.tolist())}]"
                
                sql = """
                INSERT INTO user_memory (tenant_id, fact, fact_embedding)
                VALUES ($1, $2, $3::vector)
                """
                await conn.execute(sql, tenant_id, fact, emb_str)
        finally:
            await conn.close()
    except Exception as e:
        print(f"Error extrayendo memoria: {e}")

async def retrieve_user_facts(tenant_id: uuid.UUID, query: str, top_k: int = 3) -> str:
    """
    Busca los hechos más relevantes del usuario basados en su pregunta actual.
    """
    conn = await asyncpg.connect(DB_DSN)
    try:
        await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
        
        query_embedding = await asyncio.to_thread(model.encode, query)
        emb_str = f"[{','.join(str(x) for x in query_embedding.tolist())}]"
        
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
    finally:
        await conn.close()
