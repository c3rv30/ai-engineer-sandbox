from typing import List, Optional
from pydantic import BaseModel, Field

class AnswerSource(BaseModel):
    document_id: str = Field(..., description="ID of the retrieved document (UUID)")
    quote: str = Field(..., description="Short excerpt from the document that supports the answer")

class StructuredAnswer(BaseModel):
    answer: str = Field(..., description="Final answer, in Markdown, based ONLY on the context documents and written in the language of the user's question")
    sources: List[AnswerSource] = Field(default_factory=list, description="List of sources the answer is based on")
    confidence_score: float = Field(..., description="Confidence in the answer, from 0.0 to 1.0", ge=0.0, le=1.0)
    requires_more_info: bool = Field(..., description="True if the context is not enough for a complete answer")
