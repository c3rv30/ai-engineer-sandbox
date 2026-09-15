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
from src.models.requests import (
    DEFAULT_TOP_K_RETRIEVE, DEFAULT_TOP_K_RERANK, MAX_TOP_K_RETRIEVE, MAX_TOP_K_RERANK,
)

async def supervisor_node(state: AgentState) -> dict:
    """
    Analiza la intención de la pregunta y decide qué camino tomar.
    """
    print("🤖 [Supervisor] Analizando consulta...")
    intent = await analyze_query(state["query"], state.get("history", []))
    
    # Preparamos las variaciones de búsqueda para el investigador
    queries = intent.search_queries if intent.search_queries else [state["query"]]
    if intent.hypothetical_document:
        queries.append(intent.hypothetical_document)
        
    # Si es una charla casual o está fuera de alcance, generamos la respuesta de inmediato
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
            # Las herramientas hacen peticiones HTTP síncronas (requests): en un hilo, para
            # que el event loop siga atendiendo mientras esperan a la red (PERF-03).
            tool_result = await asyncio.to_thread(tool_func, **intent.tool_args)
            ans = f"¡Herramienta ejecutada ({intent.tool_name})! Resultado:\n\n{tool_result}"
        else:
            ans = f"Error: Herramienta '{intent.tool_name}' no encontrada."
            
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

def retrieval_window(base_retrieve: int, base_rerank: int, iteration: int) -> tuple[int, int]:
    """Candidatos por variante y documentos tras el re-ranking para la pasada `iteration` (0 = la primera).

    Un reintento del ciclo de auto-corrección llega porque el redactor dijo que el
    contexto no le bastaba, y repetir la misma búsqueda devolvería exactamente lo mismo
    (BUG-05). En cada reintento se multiplican los candidatos y se deja pasar la mitad
    más de documentos (redondeando hacia arriba), sin superar los máximos de la API.
    """
    retrieve_k = min(base_retrieve * (iteration + 1), MAX_TOP_K_RETRIEVE)
    rerank_k = min(base_rerank + (base_rerank + 1) // 2 * iteration, MAX_TOP_K_RERANK)
    return retrieve_k, rerank_k

async def researcher_node(state: AgentState) -> dict:
    """
    Se encarga de buscar en Postgres Vector y GraphRAG.
    """
    print("🔍 [Investigador] Buscando contexto en la base de datos...")
    tenant_id = state["tenant_id"]
    queries = state["search_queries"]
    # La base la fija el cliente en el ChatRequest; un estado construido sin ella (fuera
    # de la API) usa los mismos valores por defecto que el contrato.
    base_retrieve = state.get("top_k_retrieve", DEFAULT_TOP_K_RETRIEVE)
    base_rerank = state.get("top_k_rerank", DEFAULT_TOP_K_RERANK)
    iteration = state.get("iterations", 0)
    top_k_retrieve, top_k_rerank = retrieval_window(base_retrieve, base_rerank, iteration)
    if iteration:
        print(f"🔄 [Investigador] Reintento {iteration}: {top_k_retrieve} candidatos por variante, {top_k_rerank} documentos.")

    # 1. Recuperación Vectorial Concurrente
    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=top_k_retrieve) for q in queries]
    results_lists = await asyncio.gather(*retrieval_tasks)
    vector_candidates = [doc for sublist in results_lists for doc in sublist]
    
    # Deduplicar
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
        
    # Reintentar solo tiene sentido si una ventana más amplia puede cambiar el contexto.
    # No puede si ninguna búsqueda llenó su cupo (el corpus no tiene más candidatos) y el
    # redactor ya los recibió todos, ni si la ventana siguiente es igual por los máximos.
    corpus_exhausted = (all(len(r) < top_k_retrieve for r in results_lists)
                        and len(unique_candidates) <= top_k_rerank)
    window_saturated = retrieval_window(base_retrieve, base_rerank, iteration + 1) == (top_k_retrieve, top_k_rerank)

    return {
        "documents": best_results,
        "iterations": state["iterations"] + 1,
        "retrieval_exhausted": corpus_exhausted or window_saturated,
    }

async def generator_node(state: AgentState) -> dict:
    """
    Genera la respuesta final. Actúa también como "Reviewer" básico.
    Si la respuesta requiere más información, marca el flag.

    Emite el texto según se genera por el canal 'custom' de LangGraph, que es
    lo que convierte a /chat/stream en streaming real y no en cuatro avisos de
    progreso. Fuera de un contexto de streaming —por ejemplo bajo el ainvoke
    de /chat/— el writer es un no-op y el nodo se comporta igual que antes.
    """
    print("✍️ [Redactor] Generando respuesta estructurada...")
    writer = get_stream_writer()

    # El canal 'messages' del estado no lo escribe ningún nodo, así que el
    # historial de la conversación viaja por 'history', igual que en el supervisor.
    kwargs = dict(
        query=state["query"],
        context=state["documents"],
        user_profile=state["user_profile"],
        history=state.get("history", [])
    )

    # El ciclo de auto-corrección puede traernos aquí por segunda vez. El cliente
    # solo sabe añadir texto (app.py:118 ignora todo lo que no haga crecer la
    # cadena), así que el reintento se anuncia y se encadena, nunca reemplaza.
    es_reintento = state.get("iterations", 0) > 1
    writer({"delta": "🔄 *Revisor: reescribiendo con el contexto ampliado...*\n\n---\n\n"
                     if es_reintento else
                     "✍️ *Redactor estructurando respuesta final...*\n\n---\n\n"})

    emitido = ""
    ultimo_parcial = None
    try:
        async for parcial in generate_answer_stream(**kwargs):
            ultimo_parcial = parcial
            texto = parcial.answer or ""
            # Instructor reemite el objeto completo en cada paso; nos quedamos
            # con lo nuevo. El texto solo puede crecer.
            if len(texto) > len(emitido):
                writer({"delta": texto[len(emitido):]})
                emitido = texto
    except Exception as e:
        print(f"⚠️ [Redactor] El streaming falló ({type(e).__name__}); se repliega a generación completa.")
        ultimo_parcial = None

    response = None
    if ultimo_parcial is not None:
        try:
            response = StructuredAnswer.model_validate(ultimo_parcial.model_dump())
        except ValidationError:
            # Parcial que nunca cerró el esquema: generación truncada por
            # max_tokens o corte a media respuesta. No se rellena a mano.
            print("⚠️ [Redactor] El parcial no completó el esquema; se repliega a generación completa.")

    if response is None:
        response = await generate_answer(**kwargs)
        # Lo ya emitido es un borrador truncado y el cliente no puede retirarlo,
        # así que se encadena la respuesta buena en lugar de sustituirla.
        writer({"delta": "\n\n---\n\n" + response.answer})

    return {
        "final_answer": response,
        "needs_more_info": response.requires_more_info
    }
