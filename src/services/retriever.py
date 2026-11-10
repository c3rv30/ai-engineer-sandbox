import uuid
import json
from typing import List
from langfuse import observe

import src.config  # noqa: F401  (loads .env)
from src.models.search import SearchResult
from src.services.db import tenant_connection
from src.services.embeddings import embed, to_pgvector

@observe(name="hybrid_search")
async def retrieve_documents(query: str, tenant_id: uuid.UUID, top_k: int = 5) -> List[SearchResult]:
    """
    Runs a hybrid search using Reciprocal Rank Fusion (RRF).
    Combines vector search (HNSW) with full-text search (ts_rank).
    """
    # The embedding is computed before taking a connection: it is CPU work and would
    # hold a pooled connection without using it.
    emb_str = to_pgvector(await embed(query))

    # 'spanish' is the language of the corpus, not of the question: the fts column is
    # generated with the same configuration (sql/01_init.sql). The supervisor writes its
    # search queries in Spanish for that reason (router.py).
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

    # The connection arrives with the tenant set, so Row Level Security (RLS) filters.
    async with tenant_connection(tenant_id) as conn:
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
