import asyncio
import os
import shutil
from pathlib import Path
from typing import List
# Before importing FlashRank: it pulls in onnxruntime, which ships a compiled telemetry
# client with its own thread. If one of its HTTP responses arrives when the interpreter
# is already shutting down, the process aborts with code 134 ("recursive_mutex lock
# failed") after finishing its work (HYG-09). Disabling it after importing FlashRank is
# not enough: the thread is already running.
try:
    import onnxruntime

    onnxruntime.disable_telemetry_events()
except Exception as e:  # onnxruntime comes as a FlashRank dependency, not our own
    print(f"Could not disable onnxruntime telemetry: {type(e).__name__}")

from flashrank import Ranker, RerankRequest
from flashrank.Config import model_file_map
from langfuse import observe
from src.models.search import SearchResult, RerankedResult

# FlashRank's default model (ms-marco-TinyBERT-L-2-v2) returned 404,
# so the MiniLM-L-12-v2 cross-encoder is pinned explicitly.
RERANKER_MODEL = "ms-marco-MiniLM-L-12-v2"

# FlashRank caches in /tmp by default, which is volatile storage. Since it decides
# whether to download by checking only that the model DIRECTORY exists (Ranker.py:80),
# a directory that survives empty means it never downloads again and the app stops
# starting for good. That is why the cache goes to a stable path.
RERANKER_CACHE_DIR = os.getenv(
    "RERANKER_CACHE_DIR", str(Path.home() / ".cache" / "flashrank")
)

def _ensure_model_cache() -> None:
    """Cleans up a model directory that exists without the model file inside.

    Covers the case FlashRank does not handle: an interrupted download, a full disk or
    a partial cleanup of the cache. Without this, FlashRank would consider the model
    downloaded and onnxruntime would fail with NO_SUCHFILE at import time.
    """
    model_dir = Path(RERANKER_CACHE_DIR) / RERANKER_MODEL
    model_file = model_dir / model_file_map[RERANKER_MODEL]
    if model_dir.exists() and not model_file.exists():
        print(f"Incomplete re-ranker cache in {model_dir}; forcing a new download.")
        shutil.rmtree(model_dir, ignore_errors=True)

print("Loading local re-ranker model (FlashRank)...")
_ensure_model_cache()
ranker = Ranker(model_name=RERANKER_MODEL, cache_dir=RERANKER_CACHE_DIR)

@observe(name="cross_encoder_rerank")
async def rerank_documents(query: str, candidates: List[SearchResult], top_k: int = 3) -> List[RerankedResult]:
    """
    Takes the retriever's candidates and reorders them with FlashRank (cross-encoder).
    """
    if not candidates:
        return []
        
    # Format FlashRank expects: a list of dictionaries with 'id' and 'text'
    passages = []
    for c in candidates:
        passages.append({
            "id": c.id,
            "text": c.content,
            "meta": c.metadata,
            "original_score": c.score
        })
        
    rerankrequest = RerankRequest(query=query, passages=passages)
    
    # FlashRank is synchronous
    results = await asyncio.to_thread(ranker.rerank, rerankrequest)
    
    # FlashRank returns the reordered list with a new 'score' key
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
