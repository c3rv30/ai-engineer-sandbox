"""Decisiones del grafo que no necesitan ni la base de datos ni el LLM.

La ventana de recuperación de cada pasada y las rutas tras el supervisor y el revisor
(BUG-05). Viven fuera de nodes.py y graph.py para poder comprobarlas sin importar los
modelos ni los clientes que cargan esos módulos (BUG-07).
"""
from src.models.requests import MAX_TOP_K_RETRIEVE, MAX_TOP_K_RERANK
# Import real, no bajo TYPE_CHECKING: LangGraph lee con get_type_hints la anotación de
# las funciones de ruta al añadir las aristas condicionales. state.py solo arrastra
# langchain_core (~0,2 s).
from src.services.agent_graph.state import AgentState


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


def is_retrieval_exhausted(result_sizes: list[int], unique_candidates: int,
                           base_retrieve: int, base_rerank: int, iteration: int) -> bool:
    """Si reintentar la pasada `iteration` con una ventana más amplia no puede cambiar el contexto.

    Reintentar solo tiene sentido si una ventana más amplia puede cambiar el contexto.
    No puede si ninguna búsqueda llenó su cupo (el corpus no tiene más candidatos) y el
    redactor ya los recibió todos, ni si la ventana siguiente es igual por los máximos.

    `result_sizes` son los candidatos que devolvió cada variante de la consulta, y
    `unique_candidates`, los que quedaron tras deduplicar.
    """
    top_k_retrieve, top_k_rerank = retrieval_window(base_retrieve, base_rerank, iteration)
    corpus_exhausted = (all(size < top_k_retrieve for size in result_sizes)
                        and unique_candidates <= top_k_rerank)
    window_saturated = retrieval_window(base_retrieve, base_rerank, iteration + 1) == (top_k_retrieve, top_k_rerank)
    return corpus_exhausted or window_saturated


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
        # (retrieval_window, más arriba).
        print("🔄 [Revisor] Falta contexto. Volviendo al Investigador con la búsqueda ampliada...")
        return "researcher"
    return "END"
