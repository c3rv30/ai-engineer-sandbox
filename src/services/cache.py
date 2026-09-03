import os
import json
import asyncio
import asyncpg
from typing import Optional
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()
DB_DSN = os.getenv("DATABASE_URL", "postgresql://app_user:apppassword@localhost:5433/postgres")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Reutilizar el mismo modelo en memoria (debería idealmente instanciarse 1 sola vez por app)
model = SentenceTransformer(EMBEDDING_MODEL)

async def check_semantic_cache(tenant_id: str, query: str, threshold: float = 0.85) -> Optional[dict]:
    """
    Busca si existe una pregunta muy similar (cosine similarity > threshold) en caché.
    Retorna el diccionario JSON con la respuesta si es un Cache Hit, sino None.
    """
    conn = await asyncpg.connect(DB_DSN)
    try:
        await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
        
        query_embedding = await asyncio.to_thread(model.encode, query)
        emb_str = f"[{','.join(str(x) for x in query_embedding.tolist())}]"
        
        # <= operator computes distance. Similarity = 1 - distance.
        sql = """
        SELECT response_json, 1 - (query_embedding <=> $1::vector) AS similarity
        FROM semantic_cache
        ORDER BY query_embedding <=> $1::vector
        LIMIT 1
        """
        row = await conn.fetchrow(sql, emb_str)
        if row and row['similarity'] >= threshold:
            print(f"✅ Cache Hit! Similitud: {row['similarity']:.4f}")
            return json.loads(row['response_json'])
            
        print("❌ Cache Miss")
        return None
    finally:
        await conn.close()

async def save_semantic_cache(tenant_id: str, query: str, response_dict: dict):
    """
    Guarda la pregunta y su respuesta en la tabla de caché semántico.
    """
    conn = await asyncpg.connect(DB_DSN)
    try:
        await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
        
        query_embedding = await asyncio.to_thread(model.encode, query)
        emb_str = f"[{','.join(str(x) for x in query_embedding.tolist())}]"
        
        sql = """
        INSERT INTO semantic_cache (tenant_id, query_text, query_embedding, response_json)
        VALUES ($1, $2, $3::vector, $4)
        """
        await conn.execute(sql, tenant_id, query, emb_str, json.dumps(response_dict))
    finally:
        await conn.close()
