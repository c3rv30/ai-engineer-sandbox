"""Single instance of the embedding model, shared by the whole process (PERF-02).

Before, retriever, cache, memory and ingestion each loaded it separately: four copies of
the model in memory and four loads in a row when importing the API.
"""
import asyncio
import threading

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
# Must match the vector(384) columns in sql/01_init.sql.
EMBEDDING_DIM = 384

# Loaded at import time, once, like the Ranker in reranker.py. Loading it on the first
# call would move several seconds of waiting onto the first request, and doing it from
# asyncio.to_thread threads could load it twice at once.
print(f"Loading local embedding model {EMBEDDING_MODEL} (once per process)...")
model = SentenceTransformer(EMBEDDING_MODEL)

_get_dimension = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
if _get_dimension() != EMBEDDING_DIM:
    raise RuntimeError(
        f"{EMBEDDING_MODEL} produces vectors of {_get_dimension()} dimensions, but the schema "
        f"expects vector({EMBEDDING_DIM}). Changing the model requires migrating sql/01_init.sql."
    )


# With torch 2.13 on macOS arm64, two threads inside model.encode at once hang or
# segfault the process (BUG-12), and both the researcher (four queries in parallel) and
# concurrent requests do exactly that. One query takes ~7 ms, so serializing is cheap.
_encode_lock = threading.Lock()


def encode(texts):
    """model.encode, one call at a time in the whole process (BUG-12). It blocks: from
    async code, call it through embed() or asyncio.to_thread."""
    with _encode_lock:
        return model.encode(texts)


async def embed(text: str):
    """Embedding of a text, computed in a thread so as not to block the event loop."""
    return await asyncio.to_thread(encode, text)


def to_pgvector(embedding) -> str:
    """The literal pgvector expects ('[x1,x2,...]'), from a numpy array or a list."""
    values = embedding.tolist() if hasattr(embedding, "tolist") else embedding
    return f"[{','.join(str(x) for x in values)}]"
