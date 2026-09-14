from langgraph.graph import StateGraph, END
from src.services.agent_graph.state import AgentState
from src.services.agent_graph.nodes import supervisor_node, researcher_node, generator_node

def route_supervisor(state: AgentState) -> str:
    # Si el supervisor ya generó una respuesta final (saludos, out_of_scope, herramientas)
    if state.get("final_answer"):
        return "END"
    return "researcher"

def route_reviewer(state: AgentState) -> str:
    # Si Claude indicó que requiere más info y no hemos iterado demasiado
    if state.get("needs_more_info") and state.get("iterations", 0) < 2:
        if state.get("retrieval_exhausted"):
            # El reintento repetiría exactamente el mismo contexto: solo añadiría coste.
            print("⏹️ [Revisor] Falta contexto, pero ampliar la búsqueda no traería nada nuevo. Se termina.")
            return "END"
        # El investigador amplía la ventana de recuperación en cada reintento
        # (retrieval_window en nodes.py).
        print("🔄 [Revisor] Falta contexto. Volviendo al Investigador con la búsqueda ampliada...")
        return "researcher"
    return "END"

def build_graph():
    workflow = StateGraph(AgentState)
    
    # Nodos
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("generator", generator_node)
    
    # Edges
    workflow.set_entry_point("supervisor")
    
    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "researcher": "researcher",
            "END": END
        }
    )
    
    workflow.add_edge("researcher", "generator")
    
    workflow.add_conditional_edges(
        "generator",
        route_reviewer,
        {
            "researcher": "researcher",
            "END": END
        }
    )
    
    return workflow.compile()
