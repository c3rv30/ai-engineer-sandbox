import asyncio
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from src.services.agent_graph.state import AgentState
from src.services.router import analyze_query
from src.services.retriever import retrieve_documents
from src.services.reranker import rerank_documents
from src.services.graphrag import retrieve_subgraph
from src.services.extractor import generate_answer
from src.services.tools import TOOLS_REGISTRY
from src.models.search import SearchResult
from src.models.structured import StructuredAnswer

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
            tool_result = tool_func(**intent.tool_args)
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

async def researcher_node(state: AgentState) -> dict:
    """
    Se encarga de buscar en Postgres Vector y GraphRAG.
    """
    print("🔍 [Investigador] Buscando contexto en la base de datos...")
    tenant_id = state["tenant_id"]
    queries = state["search_queries"]
    
    # 1. Recuperación Vectorial Concurrente
    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=15) for q in queries]
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
    best_results = await rerank_documents(state["query"], unique_candidates, top_k=10)
    
    # 3. GraphRAG
    graph_context = await retrieve_subgraph(tenant_id, state["query"])
    if graph_context:
        best_results.insert(0, SearchResult(
            id="graphrag-subgraph",
            content=graph_context,
            metadata={"source": "GraphRAG Local Database"},
            score=1.0
        ))
        
    return {"documents": best_results, "iterations": state["iterations"] + 1}

async def generator_node(state: AgentState) -> dict:
    """
    Genera la respuesta final. Actúa también como "Reviewer" básico.
    Si la respuesta requiere más información, marca el flag.
    """
    print("✍️ [Redactor] Generando respuesta estructurada...")
    
    # En un LangGraph complejo, el generator lee todo el historial (messages) 
    # pero aquí reutilizaremos nuestra robusta función estructurada.
    
    response = await generate_answer(
        query=state["query"], 
        context=state["documents"], 
        user_profile=state["user_profile"]
    )
    
    return {
        "final_answer": response,
        "needs_more_info": response.requires_more_info
    }
