from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class SearchResult(BaseModel):
    id: str = Field(..., description="ID del documento en BD")
    content: str = Field(..., description="Contenido del chunk")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadatos")
    score: float = Field(..., description="Puntaje de similitud (Vector, FTS, o RRF)")

class RerankedResult(SearchResult):
    rerank_score: float = Field(..., description="Puntaje dado por el reranker (Cross-Encoder)")
