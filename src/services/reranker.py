import asyncio
from typing import List
from flashrank import Ranker, RerankRequest
from langfuse import observe
from src.models.search import SearchResult, RerankedResult

# FlashRank inicializa el modelo local (ej. ms-marco-TinyBERT o similar)
# El modelo por defecto es muy rápido en CPU
print("Cargando modelo local de Re-ranker (FlashRank)...")
ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp/flashrank")

@observe(name="cross_encoder_rerank")
async def rerank_documents(query: str, candidates: List[SearchResult], top_k: int = 3) -> List[RerankedResult]:
    """
    Toma los candidatos del retriever y los re-ordena usando FlashRank (Cross-Encoder).
    """
    if not candidates:
        return []
        
    # Formato esperado por FlashRank: lista de diccionarios con 'id' y 'text'
    passages = []
    for c in candidates:
        passages.append({
            "id": c.id,
            "text": c.content,
            "meta": c.metadata,
            "original_score": c.score
        })
        
    rerankrequest = RerankRequest(query=query, passages=passages)
    
    # FlashRank es sincrónico
    results = await asyncio.to_thread(ranker.rerank, rerankrequest)
    
    # FlashRank devuelve la lista reordenada con una llave 'score' nueva
    final_results = []
    for r in results[:top_k]:
        final_results.append(RerankedResult(
            id=r['id'],
            content=r['text'],
            metadata=r.get('meta', {}),
            score=r.get('original_score', 0.0),
            rerank_score=r['score']
        ))
        
    return final_results
