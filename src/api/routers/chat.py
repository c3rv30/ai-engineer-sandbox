from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
import asyncio
import json

from src.models.requests import ChatRequest
from src.models.structured import StructuredAnswer
from src.api.auth import get_current_user, User
from src.services.cache import check_semantic_cache, save_semantic_cache
from src.services.memory import retrieve_user_facts, extract_and_save_facts

from src.services.evaluator import evaluate_rag_response

# --- LangGraph ---
from src.services.agent_graph.graph import build_graph
from src.services.agent_graph.state import AgentState

router = APIRouter(prefix="/chat", tags=["Chat"])

# Instanciamos el grafo una vez (es thread-safe)
agent_graph = build_graph()

@router.post("/", response_model=StructuredAnswer)
async def chat_endpoint(request: ChatRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    try:
        # 1. Caché Semántico
        cached_data = await check_semantic_cache(current_user.tenant_id, request.query)
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
        await save_semantic_cache(current_user.tenant_id, request.query, structured_response.model_dump())
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
            cached_data = await check_semantic_cache(current_user.tenant_id, request.query)
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
                intent_type="",
                search_queries=[],
                documents=[],
                final_answer=None,
                iterations=0,
                needs_more_info=False
            )
            
            # Usamos astream() de LangGraph para capturar el progreso de los nodos
            final_dict = None
            accumulated_answer = ""
            retrieved_docs = []
            async for output in agent_graph.astream(initial_state):
                for node_name, state_update in output.items():
                    if node_name == "supervisor":
                        accumulated_answer += "🤖 *Supervisor evaluando estrategia...*\n\n"
                        yield f"data: {json.dumps({'answer': accumulated_answer, 'sources': []})}\n\n"
                    elif node_name == "researcher":
                        if "documents" in state_update:
                            retrieved_docs = state_update["documents"]
                        accumulated_answer += "🔍 *Investigador buscando en Postgres Vector y GraphRAG...*\n\n"
                        yield f"data: {json.dumps({'answer': accumulated_answer, 'sources': []})}\n\n"
                    elif node_name == "generator":
                        accumulated_answer += "✍️ *Redactor estructurando respuesta final...*\n\n---\n\n"
                        yield f"data: {json.dumps({'answer': accumulated_answer, 'sources': []})}\n\n"
                        
                        if "final_answer" in state_update and state_update["final_answer"]:
                            final_dict = state_update["final_answer"].model_dump()
                            # Anexamos la respuesta final real
                            final_dict["answer"] = accumulated_answer + (final_dict.get("answer") or "")
                            yield f"data: {json.dumps(final_dict)}\n\n"
                            
            if final_dict:
                await save_semantic_cache(current_user.tenant_id, request.query, final_dict)
            background_tasks.add_task(extract_and_save_facts, current_user.tenant_id, request.query)
            
            if retrieved_docs and final_dict:
                background_tasks.add_task(evaluate_rag_response, current_user.tenant_id, request.query, final_dict.get("answer", ""), retrieved_docs)
                
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
