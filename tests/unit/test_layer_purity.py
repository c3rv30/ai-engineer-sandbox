"""Guardián de la capa de lógica pura.

Los tests de tests/unit/ no deben cargar modelos ni crear clientes de LLM. Basta con
que alguien añada a un módulo puro una importación de nodes.py o de un servicio para
que la capa vuelva a tardar ~10 s y a depender del entorno, sin que ningún otro test
falle. Este lo detecta.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Todo lo que importan los tests de tests/unit/.
MODULOS_PUROS = [
    "src.services.cache_policy",
    "src.services.agent_graph.routing",
    "src.services.history",
    "src.services.filenames",
    "src.services.db",
    "src.models.requests",
    "src.models.evaluation",
]

PROHIBIDOS = ["sentence_transformers", "flashrank", "anthropic", "langgraph"]


def test_los_modulos_puros_no_cargan_modelos_ni_clientes():
    # En un subproceso limpio: en este proceso, otros tests o plugins pueden haber
    # importado ya cualquiera de los prohibidos.
    codigo = (
        "import sys\n"
        f"for m in {MODULOS_PUROS!r}: __import__(m)\n"
        f"print('PROHIBIDOS=' + ','.join(p for p in {PROHIBIDOS!r} if p in sys.modules))\n"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert resultado.returncode == 0, resultado.stderr
    # Última línea: los módulos pesados imprimen al cargarse ("Cargando modelo...").
    cargados = resultado.stdout.strip().splitlines()[-1] if resultado.stdout.strip() else ""
    assert cargados.startswith("PROHIBIDOS="), resultado.stdout
    assert cargados == "PROHIBIDOS=", f"los módulos puros arrastran: {cargados.removeprefix('PROHIBIDOS=')}"
