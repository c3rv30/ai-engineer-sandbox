"""Regresión del historial de conversación (BUG-03).

El historial lo envía el cliente: debe llegar al prompt acotado a los últimos turnos y
sin que un turno malformado tumbe la petición.
"""
import pytest

from src.services.history import format_history


def turno(i):
    return {"role": "user" if i % 2 == 0 else "assistant", "content": f"mensaje {i}"}


def test_ventana_de_los_cuatro_ultimos_turnos_en_orden():
    resultado = format_history([turno(i) for i in range(6)])
    lineas = resultado.splitlines()
    assert lineas[0] == "Historial reciente de la conversación:"
    assert lineas[1:] == ["- USER: mensaje 2", "- ASSISTANT: mensaje 3", "- USER: mensaje 4", "- ASSISTANT: mensaje 5"]


def test_turnos_malformados_se_descartan():
    historial = [
        "no soy un diccionario",
        {"role": "user"},
        {"content": "sin rol"},
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "válido"},
    ]
    assert format_history(historial) == "Historial reciente de la conversación:\n- ASSISTANT: válido\n"


@pytest.mark.parametrize("historial", [None, [], [{"role": "user"}], ["texto", 3]])
def test_historial_vacio_o_inutilizable(historial):
    assert format_history(historial) == ""
