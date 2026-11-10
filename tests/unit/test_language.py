"""Regression of the answer language (BUG-11).

The generator gets an order naming the decided language, and the detector tells
Spanish from English and admits when it cannot tell: an undetermined answer is never
counted as a mismatch.
"""
import pytest

from src.services.language import (
    SUPPORTED_LANGUAGES,
    answer_instruction,
    check_answer_language,
    detect_language,
)

# The shape of a real answer: a Markdown paragraph that mixes in company and technology
# names, which are the same in both languages.
SPANISH_ANSWER = (
    "Bryan trabajó en **Itaú** como Data Engineer entre 2019 y 2021. Allí diseñó pipelines "
    "de datos con Airflow, Spark y AWS Glue para el área de riesgo, y migró los procesos "
    "batch a Kubernetes con Terraform."
)
ENGLISH_ANSWER = (
    "Bryan worked at **Itaú** as a Data Engineer between 2019 and 2021. There he designed "
    "data pipelines with Airflow, Spark and AWS Glue for the risk area, and moved the batch "
    "processes to Kubernetes with Terraform."
)


def test_instruction_names_the_decided_language():
    assert "Write 'answer' in English" in answer_instruction("en")
    assert "Write 'answer' in Spanish" in answer_instruction("es")


@pytest.mark.parametrize("language", ["", "English", "pt", None])
def test_instruction_rejects_an_unsupported_language(language):
    with pytest.raises(ValueError):
        answer_instruction(language)


def test_only_spanish_and_english_are_supported():
    assert set(SUPPORTED_LANGUAGES) == {"es", "en"}


@pytest.mark.parametrize("text, language", [(SPANISH_ANSWER, "es"), (ENGLISH_ANSWER, "en")])
def test_detects_a_paragraph_with_technology_names(text, language):
    assert detect_language(text) == language


@pytest.mark.parametrize("text", [None, "", "Hi!", "OK", "¡Hola!"])
def test_too_little_text_is_undetermined(text):
    assert detect_language(text) is None


def test_code_does_not_count_as_english():
    # Only code and a URL: no prose left to judge.
    answer = "```python\nfor doc in documents:\n    return doc.content\n```\nhttps://github.com/c3rv30"
    assert detect_language(answer) is None


def test_code_inside_a_spanish_answer_does_not_flip_it():
    answer = SPANISH_ANSWER + "\n\n```python\nfor item in items:\n    print(item)\n```"
    assert detect_language(answer) == "es"


def test_mismatch():
    check = check_answer_language("en", SPANISH_ANSWER)
    assert (check.expected, check.detected, check.mismatch) == ("en", "es", True)


def test_match():
    assert not check_answer_language("en", ENGLISH_ANSWER).mismatch


@pytest.mark.parametrize("expected, answer", [("en", "Hi!"), ("", SPANISH_ANSWER), (None, SPANISH_ANSWER)])
def test_unknown_side_is_never_a_mismatch(expected, answer):
    assert not check_answer_language(expected, answer).mismatch
