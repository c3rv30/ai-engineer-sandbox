from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# Únicos valores por defecto de la recuperación: los importan el investigador y el
# router de chat. Antes el contrato decía 7 y el código usaba 10 (BUG-06).
DEFAULT_TOP_K_RETRIEVE = 15
DEFAULT_TOP_K_RERANK = 10

class ChatRequest(BaseModel):
    query: str
    history: List[Dict[str, str]] = Field(default_factory=list, description="Historial de mensajes previos")
    # Los límites evitan un LIMIT negativo en Postgres y acotan el coste: la búsqueda se
    # repite por cada variante de la consulta (original, Multi-Query y HyDE) y todos los
    # candidatos pasan por el cross-encoder.
    top_k_retrieve: int = Field(DEFAULT_TOP_K_RETRIEVE, ge=1, le=50,
                                description="Candidatos de la búsqueda híbrida por cada variante de la consulta")
    top_k_rerank: int = Field(DEFAULT_TOP_K_RERANK, ge=1, le=20,
                              description="Documentos que sobreviven al re-ranking y llegan al redactor")

class IngestRequest(BaseModel):
    file_path: str
