"""Graph decisions that need neither the database nor the LLM.

The retrieval window of each pass and the routes after the supervisor and the reviewer
(BUG-05). They live outside nodes.py and graph.py so they can be checked without
importing the models and clients those modules load (BUG-07).
"""
from src.models.requests import MAX_TOP_K_RETRIEVE, MAX_TOP_K_RERANK
# A real import, not under TYPE_CHECKING: LangGraph reads the annotation of the route
# functions with get_type_hints when adding the conditional edges. state.py only pulls
# in langchain_core (~0.2 s).
from src.services.agent_graph.state import AgentState


def retrieval_window(base_retrieve: int, base_rerank: int, iteration: int) -> tuple[int, int]:
    """Candidates per variant and documents after re-ranking for pass `iteration` (0 = the first).

    A retry of the self-correction loop happens because the generator said the context
    was not enough, and repeating the same search would return exactly the same thing
    (BUG-05). On each retry the candidates are multiplied and half as many documents
    again are let through (rounding up), without exceeding the API maximums.
    """
    retrieve_k = min(base_retrieve * (iteration + 1), MAX_TOP_K_RETRIEVE)
    rerank_k = min(base_rerank + (base_rerank + 1) // 2 * iteration, MAX_TOP_K_RERANK)
    return retrieve_k, rerank_k


def is_retrieval_exhausted(result_sizes: list[int], unique_candidates: int,
                           base_retrieve: int, base_rerank: int, iteration: int) -> bool:
    """Whether retrying pass `iteration` with a wider window cannot change the context.

    Retrying only makes sense if a wider window can change the context. It cannot if no
    search filled its quota (the corpus has no more candidates) and the generator
    already received all of them, nor if the next window is the same because of the maximums.

    `result_sizes` are the candidates each query variant returned, and
    `unique_candidates`, the ones left after deduplication.
    """
    top_k_retrieve, top_k_rerank = retrieval_window(base_retrieve, base_rerank, iteration)
    corpus_exhausted = (all(size < top_k_retrieve for size in result_sizes)
                        and unique_candidates <= top_k_rerank)
    window_saturated = retrieval_window(base_retrieve, base_rerank, iteration + 1) == (top_k_retrieve, top_k_rerank)
    return corpus_exhausted or window_saturated


def route_supervisor(state: AgentState) -> str:
    # If the supervisor already produced a final answer (greetings, out_of_scope, tools)
    if state.get("final_answer"):
        return "END"
    return "researcher"

def route_reviewer(state: AgentState) -> str:
    # If Claude said it needs more info and we have not iterated too much
    if state.get("needs_more_info") and state.get("iterations", 0) < 2:
        if state.get("retrieval_exhausted"):
            # The retry would repeat exactly the same context: it would only add cost.
            print("⏹️ [Reviewer] Context is missing, but widening the search would bring nothing new. Ending.")
            return "END"
        # The researcher widens the retrieval window on each retry
        # (retrieval_window, above).
        print("🔄 [Reviewer] Context is missing. Back to the Researcher with a wider search...")
        return "researcher"
    return "END"
