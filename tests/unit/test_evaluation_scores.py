"""Regresión de los límites de las puntuaciones del evaluador (DOC-02).

Una puntuación fuera de 0–1 debe fallar en la validación de Pydantic, donde Instructor
reintenta, y no en el CHECK de SQL, donde la evaluación se perdía sin avisar.
"""
import pytest
from pydantic import ValidationError

from src.services.evaluator import RAGEvaluation

VALIDA = {
    "faithfulness_score": 0.8,
    "relevance_score": 1.0,
    "context_precision_score": 0.0,
    "reasoning": "Fiel al contexto.",
}


def test_puntuaciones_en_rango():
    RAGEvaluation(**VALIDA)


@pytest.mark.parametrize("campo", ["faithfulness_score", "relevance_score", "context_precision_score"])
@pytest.mark.parametrize("valor", [-0.01, 1.2])
def test_puntuacion_fuera_de_rango(campo, valor):
    with pytest.raises(ValidationError):
        RAGEvaluation(**{**VALIDA, campo: valor})
