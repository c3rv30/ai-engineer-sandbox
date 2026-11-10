"""BUG-12: the embedding model runs one encode at a time in the whole process.

With torch 2.13 on macOS arm64, two threads inside model.encode at once hang or kill
the process. The model is doubled here, so the test never runs two real encodes at
once: that is the defect itself, and it would hang or crash the run instead of failing.
It lives in this layer because the application it imports already loads the model.
"""
import asyncio
import threading
import time

import numpy as np

from src.services import embeddings, ingestion


class OverlapModel:
    """Stands in for the model and records how many calls were inside encode at once."""

    def __init__(self):
        self.inside = 0
        self.most_inside = 0
        self.calls = []
        self._count = threading.Lock()

    def encode(self, texts):
        with self._count:
            self.inside += 1
            self.most_inside = max(self.most_inside, self.inside)
            self.calls.append(texts)
        time.sleep(0.05)  # long enough for the other threads to arrive
        with self._count:
            self.inside -= 1
        if isinstance(texts, str):
            return np.ones(embeddings.EMBEDDING_DIM)
        return np.ones((len(texts), embeddings.EMBEDDING_DIM))


async def test_the_researchers_parallel_queries_do_not_overlap(monkeypatch):
    model = OverlapModel()
    monkeypatch.setattr(embeddings, "model", model)

    vectors = await asyncio.gather(*(embeddings.embed(f"query {i}") for i in range(4)))

    assert len(vectors) == 4 and len(model.calls) == 4
    assert model.most_inside == 1


async def test_ingestion_waits_for_the_same_lock(monkeypatch):
    # A document being ingested while a chat request embeds its query.
    model = OverlapModel()
    monkeypatch.setattr(embeddings, "model", model)
    content = "First sentence of the document. A second one. And a third one."

    chunks, *_ = await asyncio.gather(
        asyncio.to_thread(ingestion.chunk_text, content, source_type="markdown"),
        embeddings.embed("query 1"),
        embeddings.embed("query 2"),
    )

    assert chunks
    # The sentences reached the doubled model, so ingestion goes through the shared encode.
    assert [len(c) for c in model.calls if isinstance(c, list)] == [3]
    assert model.most_inside == 1
