"""Regression of the semantic cache policy (BUG-02, BUG-06, BUG-10).

The cache is checked before the supervisor and matches only by similarity of the
question text, so it can only store answers that hold for any similar request.
"""
import pytest
from pydantic import ValidationError

from src.services.cache_policy import is_cacheable, is_cache_eligible, uses_default_retrieval
from src.models.requests import ChatRequest

GOOD = {"requires_more_info": False, "confidence_score": 0.9}


# --- BUG-02: which answers may be stored ---

@pytest.mark.parametrize("intent", ["tool_execution", "out_of_scope", "made_up", None, ""])
def test_non_cacheable_intent(intent):
    # A cached tool call returned the bitcoin price to someone asking about ethereum.
    assert not is_cacheable(intent, GOOD)


@pytest.mark.parametrize("intent", ["knowledge_search", "casual_greeting"])
def test_reusable_answer(intent):
    assert is_cacheable(intent, GOOD)


def test_answer_that_asks_for_more_information():
    assert not is_cacheable("knowledge_search", {"requires_more_info": True, "confidence_score": 0.9})


@pytest.mark.parametrize("confidence", [0.49, 0.0, None])
def test_insufficient_or_missing_confidence(confidence):
    assert not is_cacheable("knowledge_search", {"requires_more_info": False, "confidence_score": confidence})


def test_confidence_without_the_field():
    assert not is_cacheable("knowledge_search", {"requires_more_info": False})


def test_confidence_at_the_threshold():
    assert is_cacheable("knowledge_search", {"requires_more_info": False, "confidence_score": 0.5})


# --- BUG-06: custom retrieval parameters ---

def test_default_parameters_use_the_cache():
    request = ChatRequest(query="Where did he work?")
    assert (request.top_k_retrieve, request.top_k_rerank) == (15, 10)
    assert uses_default_retrieval(request)
    assert is_cache_eligible(request)


@pytest.mark.parametrize("fields", [{"top_k_retrieve": 14}, {"top_k_rerank": 3}, {"top_k_retrieve": 50, "top_k_rerank": 20}])
def test_custom_parameters_do_not_use_the_cache(fields):
    request = ChatRequest(query="Where did he work?", **fields)
    assert not uses_default_retrieval(request)
    assert not is_cache_eligible(request)


@pytest.mark.parametrize("fields", [
    {"top_k_retrieve": 0}, {"top_k_retrieve": -1}, {"top_k_retrieve": 51},
    {"top_k_rerank": 0}, {"top_k_rerank": 21},
])
def test_out_of_range_parameters(fields):
    with pytest.raises(ValidationError):
        ChatRequest(query="Where did he work?", **fields)


@pytest.mark.parametrize("fields", [{"top_k_retrieve": 1, "top_k_rerank": 1}, {"top_k_retrieve": 50, "top_k_rerank": 20}])
def test_parameters_at_the_limits(fields):
    ChatRequest(query="Where did he work?", **fields)


# --- BUG-10: history ---

def test_request_with_history_does_not_use_the_cache():
    # Two conversations ending in "And in which years was that?" shared an entry.
    request = ChatRequest(
        query="And in which years was that?",
        history=[{"role": "user", "content": "Did he work at Itaú?"}, {"role": "assistant", "content": "Yes."}],
    )
    assert uses_default_retrieval(request)
    assert not is_cache_eligible(request)
