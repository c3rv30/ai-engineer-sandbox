from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ChatRequest(BaseModel):
    query: str
    history: List[Dict[str, str]] = Field(default_factory=list, description="Historial de mensajes previos")
    top_k_retrieve: int = 15
    top_k_rerank: int = 7

class IngestRequest(BaseModel):
    file_path: str
