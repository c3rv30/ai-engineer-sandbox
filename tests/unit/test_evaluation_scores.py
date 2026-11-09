"""Regression of the bounds of the evaluator's scores (DOC-02).

A score outside 0-1 must fail in Pydantic validation, where Instructor retries, and not
at the SQL CHECK, where the evaluation was lost without warning.
"""
import pytest
from pydantic import ValidationError

from src.models.evaluation import RAGEvaluation

VALID = {
    "faithfulness_score": 0.8,
    "relevance_score": 1.0,
    "context_precision_score": 0.0,
    "reasoning": "Faithful to the context.",
}


def test_scores_in_range():
    RAGEvaluation(**VALID)


@pytest.mark.parametrize("field", ["faithfulness_score", "relevance_score", "context_precision_score"])
@pytest.mark.parametrize("value", [-0.01, 1.2])
def test_score_out_of_range(field, value):
    with pytest.raises(ValidationError):
        RAGEvaluation(**{**VALID, field: value})
