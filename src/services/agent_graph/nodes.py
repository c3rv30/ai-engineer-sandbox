import asyncio
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.config import get_stream_writer
from pydantic import ValidationError
from src.services.agent_graph.state import AgentState
from src.services.router import analyze_query
from src.services.retriever import retrieve_documents
from src.services.reranker import rerank_documents
from src.services.graphrag import retrieve_subgraph
from src.services.extractor import generate_answer, generate_answer_stream
from src.services.tools import TOOLS_REGISTRY
from src.models.search import SearchResult
from src.models.structured import StructuredAnswer
from src.models.requests import DEFAULT_TOP_K_RETRIEVE, DEFAULT_TOP_K_RERANK
from src.services.agent_graph.routing import is_retrieval_exhausted, retrieval_window

async def supervisor_node(state: AgentState) -> dict:
    """
    Analyzes the intent of the question and decides which path to take.
    """
    print("🤖 [Supervisor] Analyzing the query...")
    intent = await analyze_query(state["query"], state.get("history", []))
    
    # Prepare the search variations for the researcher
    queries = intent.search_queries if intent.search_queries else [state["query"]]
    if intent.hypothetical_document:
        queries.append(intent.hypothetical_document)
        
    # Small talk or out of scope: the answer is produced right away
    if intent.intent_type in ["casual_greeting", "out_of_scope"]:
        return {
            "intent_type": intent.intent_type,
            "final_answer": StructuredAnswer(
                answer=intent.direct_answer,
                sources=[],
                confidence_score=1.0,
                requires_more_info=False
            )
        }
        
    if intent.intent_type == "tool_execution":
        tool_func = TOOLS_REGISTRY.get(intent.tool_name)
        if tool_func:
            # The tools make synchronous HTTP requests (requests): in a thread, so the
            # event loop keeps serving while they wait on the network (PERF-03).
            tool_result = await asyncio.to_thread(tool_func, **intent.tool_args)
            ans = f"Tool executed ({intent.tool_name})! Result:\n\n{tool_result}"
        else:
            ans = f"Error: tool '{intent.tool_name}' not found."
            
        return {
            "intent_type": "tool_execution",
            "final_answer": StructuredAnswer(
                answer=ans,
                sources=[],
                confidence_score=1.0,
                requires_more_info=False
            )
        }
        
    return {
        "intent_type": intent.intent_type,
        "search_queries": queries,
        "iterations": state.get("iterations", 0)
    }

async def researcher_node(state: AgentState) -> dict:
    """
    Searches pgvector and GraphRAG.
    """
    print("🔍 [Researcher] Searching the database for context...")
    tenant_id = state["tenant_id"]
    queries = state["search_queries"]
    # The client sets the base in the ChatRequest; a state built without it (outside
    # the API) uses the same defaults as the contract.
    base_retrieve = state.get("top_k_retrieve", DEFAULT_TOP_K_RETRIEVE)
    base_rerank = state.get("top_k_rerank", DEFAULT_TOP_K_RERANK)
    iteration = state.get("iterations", 0)
    top_k_retrieve, top_k_rerank = retrieval_window(base_retrieve, base_rerank, iteration)
    if iteration:
        print(f"🔄 [Researcher] Retry {iteration}: {top_k_retrieve} candidates per variant, {top_k_rerank} documents.")

    # 1. Concurrent vector retrieval
    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=top_k_retrieve) for q in queries]
    results_lists = await asyncio.gather(*retrieval_tasks)
    vector_candidates = [doc for sublist in results_lists for doc in sublist]
    
    # Deduplicate
    seen = set()
    unique_candidates = []
    for doc in vector_candidates:
        if doc.content not in seen:
            seen.add(doc.content)
            unique_candidates.append(doc)
            
    # 2. Re-ranking
    best_results = await rerank_documents(state["query"], unique_candidates, top_k=top_k_rerank)
    
    # 3. GraphRAG
    graph_context = await retrieve_subgraph(tenant_id, state["query"])
    if graph_context:
        best_results.insert(0, SearchResult(
            id="graphrag-subgraph",
            content=graph_context,
            metadata={"source": "GraphRAG Local Database"},
            score=1.0
        ))
        
    return {
        "documents": best_results,
        "iterations": state["iterations"] + 1,
        "retrieval_exhausted": is_retrieval_exhausted(
            [len(r) for r in results_lists], len(unique_candidates), base_retrieve, base_rerank, iteration,
        ),
    }

async def generator_node(state: AgentState) -> dict:
    """
    Generates the final answer. It also acts as a basic "Reviewer":
    if the answer needs more information, it sets the flag.

    It emits the text as it is generated on LangGraph's 'custom' channel, which is
    what makes /chat/stream real streaming rather than four progress notices.
    Outside a streaming context (for example under the ainvoke of /chat/) the
    writer is a no-op and the node behaves as before.
    """
    print("✍️ [Generator] Generating the structured answer...")
    writer = get_stream_writer()

    # No node writes the state's 'messages' channel, so the conversation history
    # travels in 'history', as in the supervisor.
    kwargs = dict(
        query=state["query"],
        context=state["documents"],
        user_profile=state["user_profile"],
        history=state.get("history", [])
    )

    # The self-correction loop can bring us here a second time. The client can only
    # append text (app.py:118 ignores anything that does not grow the string), so the
    # retry is announced and chained, it never replaces.
    is_retry = state.get("iterations", 0) > 1
    writer({"delta": "🔄 *Reviewer: rewriting with the wider context...*\n\n---\n\n"
                     if is_retry else
                     "✍️ *Generator writing the final answer...*\n\n---\n\n"})

    emitted = ""
    last_partial = None
    try:
        async for partial in generate_answer_stream(**kwargs):
            last_partial = partial
            text = partial.answer or ""
            # Instructor re-emits the whole object at every step; we keep only what
            # is new. The text can only grow.
            if len(text) > len(emitted):
                writer({"delta": text[len(emitted):]})
                emitted = text
    except Exception as e:
        print(f"⚠️ [Generator] Streaming failed ({type(e).__name__}); falling back to full generation.")
        last_partial = None

    response = None
    if last_partial is not None:
        try:
            response = StructuredAnswer.model_validate(last_partial.model_dump())
        except ValidationError:
            # A partial that never completed the schema: generation truncated by
            # max_tokens or cut off mid-answer. It is not filled in by hand.
            print("⚠️ [Generator] The partial did not complete the schema; falling back to full generation.")

    if response is None:
        response = await generate_answer(**kwargs)
        # What was already emitted is a truncated draft and the client cannot take it
        # back, so the good answer is chained instead of replacing it.
        writer({"delta": "\n\n---\n\n" + response.answer})

    return {
        "final_answer": response,
        "needs_more_info": response.requires_more_info
    }
