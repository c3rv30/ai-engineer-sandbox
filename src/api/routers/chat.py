from fastapi import APIRouter, HTTPException, Depends
from src.models.requests import ChatRequest
from src.models.structured import StructuredAnswer
from src.services.retriever import retrieve_documents
from src.services.reranker import rerank_documents
from src.services.extractor import generate_answer
from src.services.router import analyze_query
from src.services.tools import TOOLS_REGISTRY
from src.api.auth import get_current_user, User
from src.services.cache import check_semantic_cache, save_semantic_cache
import asyncio
import json

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post("/", response_model=StructuredAnswer)
async def chat_endpoint(request: ChatRequest, current_user: User = Depends(get_current_user)):
    try:
        # --- Fase 4: Caché Semántico ---
        cached_data = await check_semantic_cache(current_user.tenant_id, request.query)
        if cached_data:
            return StructuredAnswer(**cached_data)

        # 1. Agentic Routing
        intent = await analyze_query(request.query, request.history)
        
        if intent.intent_type in ["casual_greeting", "out_of_scope"]:
            return StructuredAnswer(
                answer=intent.direct_answer,
                sources=[],
                confidence_score=1.0,
                requires_more_info=False
            )
            
        if intent.intent_type == "tool_execution":
            tool_func = TOOLS_REGISTRY.get(intent.tool_name)
            if tool_func:
                tool_result = tool_func(**intent.tool_args)
                return StructuredAnswer(
                    answer=f"¡Herramienta ejecutada ({intent.tool_name})! Resultado:\n\n{tool_result}",
                    sources=[],
                    confidence_score=1.0,
                    requires_more_info=False
                )
            else:
                return StructuredAnswer(
                    answer=f"Error: Herramienta '{intent.tool_name}' no encontrada en el registro.",
                    sources=[],
                    confidence_score=0.0,
                    requires_more_info=True
                )
                
        # --- Fase 4: HyDE & Multi-Query Transformation ---
        queries_to_search = intent.search_queries if intent.search_queries else [request.query]
        if intent.hypothetical_document:
            queries_to_search.append(intent.hypothetical_document)
            
        # 2. Recuperación Concurrente
        retrieval_tasks = [
            retrieve_documents(q, current_user.tenant_id, top_k=max(request.top_k_retrieve, 15))
            for q in queries_to_search
        ]
        results_lists = await asyncio.gather(*retrieval_tasks)
        vector_candidates = [doc for sublist in results_lists for doc in sublist]
        
        # Deduplicar por contenido exacto
        seen = set()
        unique_candidates = []
        for doc in vector_candidates:
            if doc.content not in seen:
                seen.add(doc.content)
                unique_candidates.append(doc)
                
        # 3. Re-ranking
        best_results = await rerank_documents(request.query, unique_candidates, top_k=request.top_k_rerank)
        
        # --- GraphRAG Extraction ---
        from src.services.graphrag import retrieve_subgraph
        from src.models.search import SearchResult
        
        graph_context = await retrieve_subgraph(current_user.tenant_id, request.query)
        if graph_context:
            best_results.insert(0, SearchResult(
                id="graphrag-subgraph",
                content=graph_context,
                metadata={"source": "GraphRAG Local Database"},
                score=1.0
            ))
        
        # 4. Generación
        structured_response = await generate_answer(request.query, best_results)
        
        # Guardar en Caché Semántico
        await save_semantic_cache(current_user.tenant_id, request.query, structured_response.model_dump())
        
        return structured_response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from fastapi.responses import StreamingResponse
from src.services.extractor import generate_answer_stream

@router.post("/stream/")
async def chat_stream_endpoint(request: ChatRequest, current_user: User = Depends(get_current_user)):
    async def sse_generator():
        try:
            # --- Fase 4: Caché Semántico ---
            cached_data = await check_semantic_cache(current_user.tenant_id, request.query)
            if cached_data:
                # Agregar bandera extra para que el frontend lo sepa
                cached_data["answer"] = "⚡ [CACHE HIT] " + cached_data.get("answer", "")
                yield f"data: {json.dumps(cached_data)}\n\n"
                return

            intent = await analyze_query(request.query, request.history)
            
            if intent.intent_type in ["casual_greeting", "out_of_scope"]:
                yield f"data: {json.dumps({'answer': intent.direct_answer, 'sources': [], 'confidence_score': 1.0})}\n\n"
                return
                
            if intent.intent_type == "tool_execution":
                tool_func = TOOLS_REGISTRY.get(intent.tool_name)
                if tool_func:
                    tool_result = tool_func(**intent.tool_args)
                    yield f"data: {json.dumps({'answer': f'¡Herramienta ejecutada ({intent.tool_name})!\\n\\n{tool_result}', 'sources': [], 'confidence_score': 1.0})}\n\n"
                return

            queries_to_search = intent.search_queries if intent.search_queries else [request.query]
            if intent.hypothetical_document:
                queries_to_search.append(intent.hypothetical_document)
                
            retrieval_tasks = [
                retrieve_documents(q, current_user.tenant_id, top_k=max(request.top_k_retrieve, 15))
                for q in queries_to_search
            ]
            results_lists = await asyncio.gather(*retrieval_tasks)
            vector_candidates = [doc for sublist in results_lists for doc in sublist]
            
            seen = set()
            unique_candidates = []
            for doc in vector_candidates:
                if doc.content not in seen:
                    seen.add(doc.content)
                    unique_candidates.append(doc)
                    
            best_results = await rerank_documents(request.query, unique_candidates, top_k=request.top_k_rerank)
            
            from src.services.graphrag import retrieve_subgraph
            from src.models.search import SearchResult
            
            graph_context = await retrieve_subgraph(current_user.tenant_id, request.query)
            if graph_context:
                best_results.insert(0, SearchResult(
                    id="graphrag-subgraph",
                    content=graph_context,
                    metadata={"source": "GraphRAG Local Database"},
                    score=1.0
                ))
            
            last_partial = None
            async for partial_json in generate_answer_stream(request.query, best_results):
                last_partial = partial_json
                yield f"data: {partial_json}\n\n"
                
            # Guardar en Caché Semántico al finalizar el stream
            if last_partial:
                final_dict = json.loads(last_partial)
                await save_semantic_cache(current_user.tenant_id, request.query, final_dict)
                
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
