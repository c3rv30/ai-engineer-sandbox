"""Regression of the self-correction loop (BUG-05).

A retry happens because the generator said the context was not enough. Repeating the
same search returned exactly the same thing, so each retry must widen the window, and
there must be no retry when widening it cannot change the context.
"""
import pytest

from src.services.agent_graph.routing import (
    is_retrieval_exhausted, retrieval_window, route_reviewer, route_supervisor,
)


# --- Retrieval window ---

def test_widening_per_retry_with_the_defaults():
    assert [retrieval_window(15, 10, i) for i in range(3)] == [(15, 10), (30, 15), (45, 20)]


def test_the_first_pass_respects_the_client_parameters():
    assert retrieval_window(7, 3, 0) == (7, 3)


def test_widening_rounds_up():
    # Half of 3 documents, rounded up, is 2 more per retry.
    assert retrieval_window(7, 3, 1) == (14, 5)


@pytest.mark.parametrize("base, iteration", [((15, 10), 3), ((15, 10), 10), ((50, 20), 1), ((40, 18), 2)])
def test_capped_at_the_api_maximums(base, iteration):
    retrieve_k, rerank_k = retrieval_window(*base, iteration)
    assert retrieve_k <= 50 and rerank_k <= 20


def test_the_window_stalls_at_the_maximums():
    assert retrieval_window(15, 10, 3) == (50, 20)
    assert retrieval_window(15, 10, 10) == (50, 20)


# --- Exhaustion: when widening cannot change the context ---

def test_corpus_exhausted():
    # Pass 0 with base 15/10: no variant filled its 15 candidates, and the 8 unique ones
    # all reached the generator already (8 <= 10).
    assert is_retrieval_exhausted([8, 5, 3], 8, 15, 10, 0)


def test_not_exhausted_if_a_search_filled_its_quota():
    # One variant returned all 15: there may be more candidates in the corpus.
    assert not is_retrieval_exhausted([15, 5, 3], 8, 15, 10, 0)


def test_not_exhausted_if_candidates_were_left_out_of_the_generator():
    # 12 unique, but only 10 passed re-ranking: widening would let more through.
    assert not is_retrieval_exhausted([12, 4, 2], 12, 15, 10, 0)


def test_no_variants_and_no_candidates():
    assert is_retrieval_exhausted([], 0, 15, 10, 0)


def test_saturated_window():
    # On pass 3, the window is already 50/20 and the next one would be the same.
    assert retrieval_window(15, 10, 3) == retrieval_window(15, 10, 4) == (50, 20)
    assert is_retrieval_exhausted([50, 50, 50], 150, 15, 10, 3)


def test_window_with_room_is_not_saturated():
    assert not is_retrieval_exhausted([15, 15, 15], 45, 15, 10, 0)


# --- Reviewer decision ---

def test_retries_if_context_is_missing_and_the_search_is_not_exhausted():
    assert route_reviewer({"needs_more_info": True, "iterations": 1, "retrieval_exhausted": False}) == "researcher"


def test_no_retry_if_the_search_is_exhausted():
    assert route_reviewer({"needs_more_info": True, "iterations": 1, "retrieval_exhausted": True}) == "END"


@pytest.mark.parametrize("iterations", [2, 3])
def test_no_retry_after_two_passes(iterations):
    assert route_reviewer({"needs_more_info": True, "iterations": iterations, "retrieval_exhausted": False}) == "END"


def test_ends_if_the_context_is_enough():
    assert route_reviewer({"needs_more_info": False, "iterations": 1, "retrieval_exhausted": False}) == "END"


def test_supervisor_ends_if_there_is_already_a_final_answer():
    assert route_supervisor({"final_answer": object()}) == "END"
    assert route_supervisor({"final_answer": None}) == "researcher"
