from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
import asyncio
import json
import logging
import uuid

from src.models.requests import ChatRequest
from src.models.structured import StructuredAnswer
from src.api.auth import get_current_user, User
from src.services.cache import check_semantic_cache, save_semantic_cache
from src.services.cache_policy import is_cacheable, is_cache_eligible, uses_default_retrieval
from src.services.memory import retrieve_user_facts, extract_and_save_facts

from src.services.evaluator import evaluate_rag_response

# --- LangGraph ---
from src.services.agent_graph.graph import build_graph
from src.services.agent_graph.state import AgentState

router = APIRouter(prefix="/chat", tags=["Chat"])

# The text of an internal exception is not returned to the client (SEC-06): it carried
# server paths and Anthropic SDK messages. It goes to the log, and the client only gets
# an identifier to correlate it with.
logger = logging.getLogger(__name__)


# The graph is built once (it is thread-safe)
agent_graph = build_graph()

@router.post("/", response_model=StructuredAnswer)
async def chat_endpoint(request: ChatRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    try:
        # 1. Semantic cache
        use_cache = is_cache_eligible(request)
        cached_data = await check_semantic_cache(current_user.tenant_id, request.query) if use_cache else None
        if cached_data:
            return StructuredAnswer(**cached_data)

        # 2. Long-Term Memory
        user_profile = await retrieve_user_facts(current_user.tenant_id, request.query)

        # 3. Initialize the graph state
        initial_state = AgentState(
            messages=[],
            tenant_id=current_user.tenant_id,
            user_profile=user_profile,
            query=request.query,
            history=request.history,
            top_k_retrieve=request.top_k_retrieve,
            top_k_rerank=request.top_k_rerank,
            intent_type="",
            answer_language="",
            search_queries=[],
            documents=[],
            final_answer=None,
            iterations=0,
            needs_more_info=False
        )

        # 4. Run the graph
        final_state = await agent_graph.ainvoke(initial_state)

        structured_response = final_state.get("final_answer")
        if not structured_response:
            raise HTTPException(status_code=500, detail="The agent graph did not return a final answer.")

        # 5. Post-response tasks
        response_dict = structured_response.model_dump()
        if use_cache and is_cacheable(final_state.get("intent_type"), response_dict):
            await save_semantic_cache(current_user.tenant_id, request.query, response_dict)
        background_tasks.add_task(extract_and_save_facts, current_user.tenant_id, request.query)

        # RAG evaluation in the background
        if final_state.get("documents"):
            background_tasks.add_task(evaluate_rag_response, current_user.tenant_id, request.query, structured_response.answer, final_state["documents"])

        return structured_response

    except HTTPException:
        # The "the graph did not return a final answer" 500 is raised by this same block
        # and already carries a message meant for the client. Without this case, the
        # generic except would rewrap it and lose that detail.
        raise
    except Exception:
        error_id = uuid.uuid4().hex[:8]
        logger.exception("POST /chat/ failed [%s]", error_id)
        raise HTTPException(status_code=500, detail=f"Internal error ({error_id})")


@router.post("/stream/")
async def chat_stream_endpoint(request: ChatRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    """
    Streaming endpoint using LangGraph.
    Emits progress events and finally the structured answer.
    """
    async def sse_generator():
        try:
            use_cache = is_cache_eligible(request)
            cached_data = await check_semantic_cache(current_user.tenant_id, request.query) if use_cache else None
            if cached_data:
                cached_data["answer"] = "⚡ [CACHE HIT] " + cached_data.get("answer", "")
                yield f"data: {json.dumps(cached_data)}\n\n"
                return

            user_profile = await retrieve_user_facts(current_user.tenant_id, request.query)

            initial_state = AgentState(
                messages=[],
                tenant_id=current_user.tenant_id,
                user_profile=user_profile,
                query=request.query,
                history=request.history,
                top_k_retrieve=request.top_k_retrieve,
                top_k_rerank=request.top_k_rerank,
                intent_type="",
                answer_language="",
                search_queries=[],
                documents=[],
                final_answer=None,
                iterations=0,
                needs_more_info=False
            )

            # Two channels at once: 'custom' carries the generator's text as it is
            # produced (generator_node writes it with get_stream_writer) and 'updates'
            # carries per-node progress and the final state.
            final_dict = None
            intent_type = None
            accumulated_answer = ""
            retrieved_docs = []
            async for mode, chunk in agent_graph.astream(initial_state, stream_mode=["updates", "custom"]):
                if mode == "custom":
                    accumulated_answer += chunk.get("delta", "")
                    yield f"data: {json.dumps({'answer': accumulated_answer, 'sources': []})}\n\n"
                    continue

                for node_name, state_update in chunk.items():
                    if state_update and state_update.get("intent_type"):
                        intent_type = state_update["intent_type"]
                    if node_name == "supervisor":
                        accumulated_answer += "🤖 *Supervisor choosing a strategy...*\n\n"
                        yield f"data: {json.dumps({'answer': accumulated_answer, 'sources': []})}\n\n"
                    elif node_name == "researcher":
                        if "documents" in state_update:
                            retrieved_docs = state_update["documents"]
                        accumulated_answer += "🔍 *Researcher searching pgvector and GraphRAG...*\n\n"
                        yield f"data: {json.dumps({'answer': accumulated_answer, 'sources': []})}\n\n"

                    if state_update and state_update.get("final_answer"):
                        # Clean object: it is the one stored in the cache and the one
                        # sent to the evaluator's judge. It must not carry the
                        # progress messages, which are UI artifacts.
                        final_dict = state_update["final_answer"].model_dump()
                        # The generator already emitted its text on the 'custom' channel.
                        # The supervisor did not: it handles greetings, out-of-scope
                        # topics and tools itself and the graph ends there, so its
                        # answer has to be appended or the client is left with the
                        # progress line and nothing else.
                        if node_name != "generator":
                            accumulated_answer += final_dict.get("answer") or ""
                        # Object for the stream: it extends the text already emitted,
                        # because the frontend renders character diffs.
                        stream_dict = {**final_dict, "answer": accumulated_answer}
                        yield f"data: {json.dumps(stream_dict)}\n\n"

            if final_dict and use_cache and is_cacheable(intent_type, final_dict):
                await save_semantic_cache(current_user.tenant_id, request.query, final_dict)
            background_tasks.add_task(extract_and_save_facts, current_user.tenant_id, request.query)

            if retrieved_docs and final_dict:
                background_tasks.add_task(evaluate_rag_response, current_user.tenant_id, request.query, final_dict.get("answer", ""), retrieved_docs)

        except Exception:
            # The 'error' key is kept: it is the one the frontend renders.
            error_id = uuid.uuid4().hex[:8]
            logger.exception("POST /chat/stream/ failed [%s]", error_id)
            yield f"data: {json.dumps({'error': f'Internal error ({error_id})'})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
