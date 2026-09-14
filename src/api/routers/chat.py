from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
import asyncio
import json

from src.models.requests import ChatRequest, DEFAULT_TOP_K_RETRIEVE, DEFAULT_TOP_K_RERANK
from src.models.structured import StructuredAnswer
from src.api.auth import get_current_user, User
from src.services.cache import check_semantic_cache, save_semantic_cache
from src.services.memory import retrieve_user_facts, extract_and_save_facts

from src.services.evaluator import evaluate_rag_response

# --- LangGraph ---
from src.services.agent_graph.graph import build_graph
from src.services.agent_graph.state import AgentState

router = APIRouter(prefix="/chat", tags=["Chat"])

# Solo se cachean respuestas que sigan valiendo la próxima vez que alguien pregunte
# algo parecido. El caché se consulta antes que el supervisor y compara por similitud,
# así que una herramienta cacheada devolvería datos viejos o de otra consulta (el
# precio de bitcoin a quien pregunta por ethereum), y un 'out_of_scope' contestaría a
# otra pregunta. Es una lista blanca porque intent_type lo escribe el LLM como texto
# libre: un valor inesperado no debe acabar en caché.
CACHEABLE_INTENTS = {"knowledge_search", "casual_greeting"}
MIN_CACHE_CONFIDENCE = 0.5


def is_cacheable(intent_type: str | None, answer: dict) -> bool:
    # Tampoco se fija para siempre una respuesta que el propio sistema da por insuficiente.
    return (intent_type in CACHEABLE_INTENTS
            and not answer.get("requires_more_info")
            and (answer.get("confidence_score") or 0) >= MIN_CACHE_CONFIDENCE)


def uses_default_retrieval(request: ChatRequest) -> bool:
    # El caché se indexa solo por la pregunta. Una respuesta obtenida con otros top_k no
    # es intercambiable con la de los valores por defecto, así que esas peticiones ni
    # leen ni escriben caché.
    return (request.top_k_retrieve == DEFAULT_TOP_K_RETRIEVE
            and request.top_k_rerank == DEFAULT_TOP_K_RERANK)

# Instanciamos el grafo una vez (es thread-safe)
agent_graph = build_graph()

@router.post("/", response_model=StructuredAnswer)
async def chat_endpoint(request: ChatRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    try:
        # 1. Caché Semántico
        use_cache = uses_default_retrieval(request)
        cached_data = await check_semantic_cache(current_user.tenant_id, request.query) if use_cache else None
        if cached_data:
            return StructuredAnswer(**cached_data)

        # 2. Long-Term Memory
        user_profile = await retrieve_user_facts(current_user.tenant_id, request.query)

        # 3. Inicializar Estado del Grafo
        initial_state = AgentState(
            messages=[],
            tenant_id=current_user.tenant_id,
            user_profile=user_profile,
            query=request.query,
            history=request.history,
            top_k_retrieve=request.top_k_retrieve,
            top_k_rerank=request.top_k_rerank,
            intent_type="",
            search_queries=[],
            documents=[],
            final_answer=None,
            iterations=0,
            needs_more_info=False
        )

        # 4. Ejecutar el Grafo
        final_state = await agent_graph.ainvoke(initial_state)

        structured_response = final_state.get("final_answer")
        if not structured_response:
            raise HTTPException(status_code=500, detail="El Grafo de Agentes no devolvió una respuesta final.")

        # 5. Tareas post-respuesta
        response_dict = structured_response.model_dump()
        if use_cache and is_cacheable(final_state.get("intent_type"), response_dict):
            await save_semantic_cache(current_user.tenant_id, request.query, response_dict)
        background_tasks.add_task(extract_and_save_facts, current_user.tenant_id, request.query)

        # Evaluación RAG en Background
        if final_state.get("documents"):
            background_tasks.add_task(evaluate_rag_response, current_user.tenant_id, request.query, structured_response.answer, final_state["documents"])

        return structured_response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream/")
async def chat_stream_endpoint(request: ChatRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    """
    Endpoint de Streaming usando LangGraph.
    Emitimos eventos de progreso y finalmente la respuesta estructurada.
    """
    async def sse_generator():
        try:
            use_cache = uses_default_retrieval(request)
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
                search_queries=[],
                documents=[],
                final_answer=None,
                iterations=0,
                needs_more_info=False
            )

            # Dos canales a la vez: 'custom' trae el texto del redactor según se
            # genera (lo escribe generator_node con get_stream_writer) y 'updates'
            # trae el progreso por nodo y el estado final.
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
                        accumulated_answer += "🤖 *Supervisor evaluando estrategia...*\n\n"
                        yield f"data: {json.dumps({'answer': accumulated_answer, 'sources': []})}\n\n"
                    elif node_name == "researcher":
                        if "documents" in state_update:
                            retrieved_docs = state_update["documents"]
                        accumulated_answer += "🔍 *Investigador buscando en Postgres Vector y GraphRAG...*\n\n"
                        yield f"data: {json.dumps({'answer': accumulated_answer, 'sources': []})}\n\n"

                    if state_update and state_update.get("final_answer"):
                        # Objeto limpio: es el que se persiste en caché y el que
                        # se envía al juez del evaluador. No debe llevar los
                        # mensajes de progreso, que son artefactos de la UI.
                        final_dict = state_update["final_answer"].model_dump()
                        # El redactor ya emitió su texto por el canal 'custom'. El
                        # supervisor no: resuelve saludos, temas fuera de alcance y
                        # herramientas él mismo y el grafo termina ahí, así que su
                        # respuesta hay que añadirla o el cliente se queda con la
                        # línea de progreso y nada más.
                        if node_name != "generator":
                            accumulated_answer += final_dict.get("answer") or ""
                        # Objeto para el stream: prolonga el texto ya emitido,
                        # porque el frontend renderiza diffs de caracteres.
                        stream_dict = {**final_dict, "answer": accumulated_answer}
                        yield f"data: {json.dumps(stream_dict)}\n\n"

            if final_dict and use_cache and is_cacheable(intent_type, final_dict):
                await save_semantic_cache(current_user.tenant_id, request.query, final_dict)
            background_tasks.add_task(extract_and_save_facts, current_user.tenant_id, request.query)

            if retrieved_docs and final_dict:
                background_tasks.add_task(evaluate_rag_response, current_user.tenant_id, request.query, final_dict.get("answer", ""), retrieved_docs)

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
