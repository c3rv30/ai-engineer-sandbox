import uuid
import json
from typing import Optional

import src.config  # noqa: F401  (loads .env)
from src.services.db import tenant_connection
from src.services.embeddings import embed, to_pgvector


async def check_semantic_cache(tenant_id: uuid.UUID, query: str, threshold: float = 0.85) -> Optional[dict]:
    """
    Looks for a very similar question (cosine similarity > threshold) in the cache.
    Returns the JSON dictionary with the answer on a Cache Hit, otherwise None.
    """
    # Computed before taking a connection: it is CPU work and would hold one from the pool.
    emb_str = to_pgvector(await embed(query))

    # <= operator computes distance. Similarity = 1 - distance.
    sql = """
    SELECT response_json, 1 - (query_embedding <=> $1::vector) AS similarity
    FROM semantic_cache
    ORDER BY query_embedding <=> $1::vector
    LIMIT 1
    """
    async with tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(sql, emb_str)

    if row and row['similarity'] >= threshold:
        print(f"✅ Cache Hit! Similarity: {row['similarity']:.4f}")
        return json.loads(row['response_json'])

    print("❌ Cache Miss")
    return None


async def save_semantic_cache(tenant_id: uuid.UUID, query: str, response_dict: dict):
    """
    Stores the question and its answer in the semantic cache table.
    """
    # Computed before taking a connection: it is CPU work and would hold one from the pool.
    emb_str = to_pgvector(await embed(query))

    sql = """
    INSERT INTO semantic_cache (tenant_id, query_text, query_embedding, response_json)
    VALUES ($1, $2, $3::vector, $4)
    """
    async with tenant_connection(tenant_id) as conn:
        await conn.execute(sql, tenant_id, query, emb_str, json.dumps(response_dict))
