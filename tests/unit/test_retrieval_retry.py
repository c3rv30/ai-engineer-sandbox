"""Regresión del ciclo de auto-corrección (BUG-05).

Un reintento llega porque el redactor dijo que el contexto no le bastaba. Repetir la
misma búsqueda devolvía exactamente lo mismo, así que cada reintento debe ampliar la
ventana, y no debe reintentarse cuando ampliarla no puede cambiar el contexto.
"""
import pytest

from src.services.agent_graph.routing import (
    is_retrieval_exhausted, retrieval_window, route_reviewer, route_supervisor,
)


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


# --- Agotamiento: cuándo ampliar no puede cambiar el contexto ---

def test_corpus_agotado():
    # Pasada 0 con base 15/10: ninguna variante llenó sus 15 candidatos, y los 8 únicos
    # ya llegaron todos al redactor (8 <= 10).
    assert is_retrieval_exhausted([8, 5, 3], 8, 15, 10, 0)


def test_no_agotado_si_alguna_busqueda_lleno_su_cupo():
    # Una variante devolvió los 15: puede haber más candidatos en el corpus.
    assert not is_retrieval_exhausted([15, 5, 3], 8, 15, 10, 0)


def test_no_agotado_si_quedaron_candidatos_fuera_del_redactor():
    # 12 únicos, pero solo 10 pasaron el re-ranking: ampliar dejaría pasar más.
    assert not is_retrieval_exhausted([12, 4, 2], 12, 15, 10, 0)


def test_sin_variantes_y_sin_candidatos():
    assert is_retrieval_exhausted([], 0, 15, 10, 0)


def test_ventana_saturada():
    # En la pasada 3, la ventana ya es 50/20 y la siguiente sería igual.
    assert retrieval_window(15, 10, 3) == retrieval_window(15, 10, 4) == (50, 20)
    assert is_retrieval_exhausted([50, 50, 50], 150, 15, 10, 3)


def test_ventana_con_margen_no_saturada():
    assert not is_retrieval_exhausted([15, 15, 15], 45, 15, 10, 0)


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
