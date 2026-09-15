"""Instancia única del modelo de embeddings, compartida por todo el proceso (PERF-02).

Antes lo cargaban por separado retriever, cache, memory e ingestion: cuatro copias del
modelo en memoria y cuatro cargas seguidas al importar la API.
"""
import asyncio

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
# Debe coincidir con las columnas vector(384) de sql/01_init.sql.
EMBEDDING_DIM = 384

# Se carga al importar, una sola vez, igual que el Ranker de reranker.py. Cargarlo en la
# primera llamada trasladaría varios segundos de espera a la primera petición, y hacerlo
# desde los hilos de asyncio.to_thread podría cargarlo dos veces a la vez.
print(f"Cargando modelo local de embedding {EMBEDDING_MODEL} (una sola vez por proceso)...")
model = SentenceTransformer(EMBEDDING_MODEL)

_get_dimension = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
if _get_dimension() != EMBEDDING_DIM:
    raise RuntimeError(
        f"{EMBEDDING_MODEL} produce vectores de {_get_dimension()} dimensiones, pero el esquema "
        f"espera vector({EMBEDDING_DIM}). Cambiar de modelo exige migrar sql/01_init.sql."
    )


async def embed(text: str):
    """Embedding de un texto, calculado en un hilo para no bloquear el event loop."""
    return await asyncio.to_thread(model.encode, text)


def to_pgvector(embedding) -> str:
    """Literal que espera pgvector ('[x1,x2,...]'), desde un array de numpy o una lista."""
    values = embedding.tolist() if hasattr(embedding, "tolist") else embedding
    return f"[{','.join(str(x) for x in values)}]"
