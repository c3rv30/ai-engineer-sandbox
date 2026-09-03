from typing import List, Optional
from pydantic import BaseModel, Field

class AnswerSource(BaseModel):
    document_id: str = Field(..., description="ID del documento recuperado (UUID)")
    quote: str = Field(..., description="Extracto corto del documento que justifica la respuesta")

class StructuredAnswer(BaseModel):
    answer: str = Field(..., description="Respuesta final, en formato Markdown, basada SOLO en los documentos de contexto")
    sources: List[AnswerSource] = Field(default_factory=list, description="Lista de fuentes en las que se basa la respuesta")
    confidence_score: float = Field(..., description="Nivel de confianza en la respuesta del 0.0 al 1.0", ge=0.0, le=1.0)
    requires_more_info: bool = Field(..., description="True si el contexto no es suficiente para dar una respuesta completa")
