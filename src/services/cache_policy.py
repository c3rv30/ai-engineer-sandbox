"""Semantic cache policy: which requests use it and which answers are stored.

It lives outside src/api/routers/chat.py so it can be checked without importing the
graph, the models or the Anthropic clients (BUG-07). It depends only on src.models.
"""
from src.models.requests import ChatRequest, DEFAULT_TOP_K_RETRIEVE, DEFAULT_TOP_K_RERANK

# Only answers that will still hold the next time someone asks something similar are
# cached. The cache is checked before the supervisor and matches by similarity, so a
# cached tool call would return stale data or another query's data (the bitcoin price
# to someone asking about ethereum), and an 'out_of_scope' would answer a different
# question. It is an allowlist because intent_type is free text written by the LLM:
# an unexpected value must not end up in the cache.
CACHEABLE_INTENTS = {"knowledge_search", "casual_greeting"}
MIN_CACHE_CONFIDENCE = 0.5


def is_cacheable(intent_type: str | None, answer: dict, *, language_mismatch: bool = False) -> bool:
    # Nor is an answer the system itself considers insufficient kept forever. Nor one in
    # the wrong language, which every similar question would get again (BUG-11). The
    # endpoint detects the language; the policy only decides.
    return (intent_type in CACHEABLE_INTENTS
            and not language_mismatch
            and not answer.get("requires_more_info")
            and (answer.get("confidence_score") or 0) >= MIN_CACHE_CONFIDENCE)


def uses_default_retrieval(request: ChatRequest) -> bool:
    # The cache is keyed only by the question. An answer obtained with other top_k values
    # is not interchangeable with the one from the defaults, so those requests neither
    # read nor write the cache.
    return (request.top_k_retrieve == DEFAULT_TOP_K_RETRIEVE
            and request.top_k_rerank == DEFAULT_TOP_K_RERANK)


def is_cache_eligible(request: ChatRequest) -> bool:
    """Whether this request may read or write the cache.

    The cache is keyed only by the question text, and since BUG-03 the answer also
    depends on the history: "And in which years was that?" means different things
    depending on the previous turn. Two conversations that end in the same follow-up
    have similarity 1.0 and share an entry (BUG-10). Reproduced against the real API:
    a follow-up about Itaú/Kabeli got the years of MisterGas, presented as "According
    to the previous history", a history that was not the user's.

    So a request with history neither reads nor writes the cache, like one with its
    own top_k. The alternative (keying by the query the supervisor already resolved)
    would keep the cache for follow-ups, but it only closes the defect if the
    supervisor always embeds the full referent, and it forces the cache to be checked
    after the supervisor, paying for its LLM call on hits too.
    """
    return uses_default_retrieval(request) and not request.history
