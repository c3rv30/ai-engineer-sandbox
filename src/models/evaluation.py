"""Structured answer of the evaluator's LLM judge (src/services/evaluator.py).

Kept out of the service so its bounds can be checked without creating the Anthropic
client that the service creates at import time (BUG-07).
"""
from pydantic import BaseModel, Field


class RAGEvaluation(BaseModel):
    # ge/le: an out-of-range score fails here, where Instructor retries by sending the
    # error back to the model, and not at the SQL CHECK, where the evaluation was lost (DOC-02).
    faithfulness_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Score from 0.0 to 1.0 for whether the answer is faithful to the context (no hallucinations)."
    )
    relevance_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Score from 0.0 to 1.0 for whether the answer directly addresses the question."
    )
    context_precision_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Score from 0.0 to 1.0 for whether the provided context held the information needed or was mostly irrelevant noise."
    )
    reasoning: str = Field(
        ...,
        description="Concise explanation of the scores, at most 3 sentences.",
        max_length=600,
    )
