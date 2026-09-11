import asyncio
import os
import shutil
from pathlib import Path
from typing import List
from flashrank import Ranker, RerankRequest
from flashrank.Config import model_file_map
from langfuse import observe
from src.models.search import SearchResult, RerankedResult

# El modelo por defecto de FlashRank (ms-marco-TinyBERT-L-2-v2) devolvía 404,
# por lo que se fija explícitamente el Cross-Encoder MiniLM-L-12-v2.
RERANKER_MODEL = "ms-marco-MiniLM-L-12-v2"

# FlashRank cachea en /tmp por defecto, que es almacenamiento volátil. Como decide
# si descargar comprobando solo si existe el DIRECTORIO del modelo (Ranker.py:80),
# un directorio que sobreviva vacío hace que no vuelva a descargar nunca y que la
# app deje de arrancar de forma permanente. Por eso el caché va a una ruta estable.
RERANKER_CACHE_DIR = os.getenv(
    "RERANKER_CACHE_DIR", str(Path.home() / ".cache" / "flashrank")
)

def _ensure_model_cache() -> None:
    """Sanea un directorio de modelo presente pero sin el archivo dentro.

    Cubre el caso que FlashRank no contempla: descarga interrumpida, disco lleno o
    limpieza parcial del caché. Sin esto, FlashRank daría el modelo por descargado
    y onnxruntime fallaría con NO_SUCHFILE en tiempo de importación.
    """
    model_dir = Path(RERANKER_CACHE_DIR) / RERANKER_MODEL
    model_file = model_dir / model_file_map[RERANKER_MODEL]
    if model_dir.exists() and not model_file.exists():
        print(f"Caché del re-ranker incompleto en {model_dir}; se fuerza la re-descarga.")
        shutil.rmtree(model_dir, ignore_errors=True)

print("Cargando modelo local de Re-ranker (FlashRank)...")
_ensure_model_cache()
ranker = Ranker(model_name=RERANKER_MODEL, cache_dir=RERANKER_CACHE_DIR)

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
