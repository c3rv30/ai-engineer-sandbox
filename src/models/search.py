from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class SearchResult(BaseModel):
    id: str = Field(..., description="Document ID in the database")
    content: str = Field(..., description="Chunk content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata")
    score: float = Field(..., description="Similarity score (vector, FTS or RRF)")

class RerankedResult(SearchResult):
    rerank_score: float = Field(..., description="Score given by the re-ranker (cross-encoder)")
