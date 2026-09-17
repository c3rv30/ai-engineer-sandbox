"""Respuesta estructurada del juez LLM del evaluador (src/services/evaluator.py).

Fuera del servicio para poder comprobar sus límites sin crear el cliente de Anthropic
que este crea al importarse (BUG-07).
"""
from pydantic import BaseModel, Field


class RAGEvaluation(BaseModel):
    # ge/le: una puntuación fuera de rango falla aquí, donde Instructor reintenta devolviéndole
    # el error al modelo, y no en el CHECK de SQL, donde la evaluación se perdía (DOC-02).
    faithfulness_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Puntuación de 0.0 a 1.0 indicando si la respuesta es fiel al contexto (sin alucinaciones)."
    )
    relevance_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Puntuación de 0.0 a 1.0 indicando si la respuesta responde directamente a la pregunta."
    )
    context_precision_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Puntuación de 0.0 a 1.0 indicando si el contexto provisto contenía la información necesaria o si había basura irrelevante."
    )
    reasoning: str = Field(
        ...,
        description="Explicación concisa de las puntuaciones, máximo 3 frases.",
        max_length=600,
    )
