from langgraph.graph import StateGraph, END
from src.services.agent_graph.state import AgentState
from src.services.agent_graph.nodes import supervisor_node, researcher_node, generator_node
from src.services.agent_graph.routing import route_supervisor, route_reviewer


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
