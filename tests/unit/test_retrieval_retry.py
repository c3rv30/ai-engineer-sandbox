"""Regresión del ciclo de auto-corrección (BUG-05).

Un reintento llega porque el redactor dijo que el contexto no le bastaba. Repetir la
misma búsqueda devolvía exactamente lo mismo, así que cada reintento debe ampliar la
ventana, y no debe reintentarse cuando ampliarla no puede cambiar el contexto.
"""
import pytest

from src.services.agent_graph.graph import route_reviewer, route_supervisor
from src.services.agent_graph.nodes import retrieval_window


# --- Ventana de recuperación ---

def test_ampliacion_por_reintento_con_los_valores_por_defecto():
    assert [retrieval_window(15, 10, i) for i in range(3)] == [(15, 10), (30, 15), (45, 20)]


def test_la_primera_pasada_respeta_los_parametros_del_cliente():
    assert retrieval_window(7, 3, 0) == (7, 3)


def test_ampliacion_redondea_hacia_arriba():
    # La mitad de 3 documentos, hacia arriba, son 2 más por reintento.
    assert retrieval_window(7, 3, 1) == (14, 5)


@pytest.mark.parametrize("base, iteracion", [((15, 10), 3), ((15, 10), 10), ((50, 20), 1), ((40, 18), 2)])
def test_tope_en_los_maximos_de_la_api(base, iteracion):
    retrieve_k, rerank_k = retrieval_window(*base, iteracion)
    assert retrieve_k <= 50 and rerank_k <= 20


def test_la_ventana_se_estanca_en_los_maximos():
    assert retrieval_window(15, 10, 3) == (50, 20)
    assert retrieval_window(15, 10, 10) == (50, 20)


# --- Decisión del revisor ---

def test_se_reintenta_si_falta_contexto_y_la_busqueda_no_esta_agotada():
    assert route_reviewer({"needs_more_info": True, "iterations": 1, "retrieval_exhausted": False}) == "researcher"


def test_no_se_reintenta_si_la_busqueda_esta_agotada():
    assert route_reviewer({"needs_more_info": True, "iterations": 1, "retrieval_exhausted": True}) == "END"


@pytest.mark.parametrize("iteraciones", [2, 3])
def test_no_se_reintenta_tras_dos_pasadas(iteraciones):
    assert route_reviewer({"needs_more_info": True, "iterations": iteraciones, "retrieval_exhausted": False}) == "END"


def test_se_termina_si_el_contexto_basta():
    assert route_reviewer({"needs_more_info": False, "iterations": 1, "retrieval_exhausted": False}) == "END"


def test_supervisor_termina_si_ya_hay_respuesta_final():
    assert route_supervisor({"final_answer": object()}) == "END"
    assert route_supervisor({"final_answer": None}) == "researcher"
