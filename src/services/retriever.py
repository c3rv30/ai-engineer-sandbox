import os
import uuid
import asyncio
import json
from typing import List
from dotenv import load_dotenv
load_dotenv()

import asyncpg
from sentence_transformers import SentenceTransformer
from langfuse import observe
from src.models.search import SearchResult

DB_DSN = os.getenv("DATABASE_URL", "postgresql://app_user:apppassword@localhost:5433/postgres")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

print(f"Cargando modelo local de embedding {EMBEDDING_MODEL} para Retriever...")
model = SentenceTransformer(EMBEDDING_MODEL)

@observe(name="hybrid_search")
async def retrieve_documents(query: str, tenant_id: uuid.UUID, top_k: int = 5) -> List[SearchResult]:
    """
    Realiza una búsqueda híbrida usando Reciprocal Rank Fusion (RRF).
    Combina Vector Search (HNSW) con Full-Text Search (BM25).
    """
    conn = await asyncpg.connect(DB_DSN)
    
    query_embedding = await asyncio.to_thread(model.encode, query)
    emb_str = f"[{','.join(str(x) for x in query_embedding.tolist())}]"
    
    try:
        # Inyectar el tenant_id actual para que aplique la Row Level Security (RLS)
        await conn.execute(f"SET app.current_tenant = '{tenant_id}'")

        sql_query = """
        WITH vector_search AS (
            SELECT id, content, metadata,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS rank
            FROM documents
            ORDER BY embedding <=> $1::vector
            LIMIT $2
        ),
        fts_search AS (
            SELECT id, content, metadata,
                   ROW_NUMBER() OVER (ORDER BY ts_rank(fts, websearch_to_tsquery('spanish', $3)) DESC) AS rank
            FROM documents
            WHERE fts @@ websearch_to_tsquery('spanish', $3)
            ORDER BY ts_rank(fts, websearch_to_tsquery('spanish', $3)) DESC
            LIMIT $2
        )
        SELECT
            COALESCE(v.id, f.id) AS id,
            COALESCE(v.content, f.content) AS content,
            COALESCE(v.metadata, f.metadata) AS metadata,
            COALESCE(1.0 / (60 + v.rank), 0.0) + COALESCE(1.0 / (60 + f.rank), 0.0) AS similarity_score
        FROM vector_search v
        FULL OUTER JOIN fts_search f ON v.id = f.id
        ORDER BY similarity_score DESC
        LIMIT $2;
        """
        
        rows = await conn.fetch(sql_query, emb_str, top_k, query)
        
        results = []
        for row in rows:
            results.append(SearchResult(
                id=str(row['id']),
                content=row['content'],
                metadata=json.loads(row['metadata']),
                score=row['similarity_score']
            ))
            
        return results
        
    finally:
        await conn.close()
