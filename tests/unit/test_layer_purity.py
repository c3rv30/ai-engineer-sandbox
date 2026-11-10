"""Guard of the pure logic layer.

The tests in tests/unit/ must not load models or create LLM clients. It only takes
someone adding an import of nodes.py or of a service to a pure module for the layer to
take ~10 s again and depend on the environment, without any other test failing. This
one catches it.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Everything the tests in tests/unit/ import.
PURE_MODULES = [
    "src.services.cache_policy",
    "src.services.agent_graph.routing",
    "src.services.history",
    "src.services.filenames",
    "src.services.db",
    "src.models.requests",
    "src.models.evaluation",
]

FORBIDDEN = ["sentence_transformers", "flashrank", "anthropic", "langgraph"]


def test_pure_modules_load_no_models_or_clients():
    # In a clean subprocess: in this process, other tests or plugins may already have
    # imported any of the forbidden ones.
    code = (
        "import sys\n"
        f"for m in {PURE_MODULES!r}: __import__(m)\n"
        f"print('FORBIDDEN=' + ','.join(p for p in {FORBIDDEN!r} if p in sys.modules))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    # Last line: the heavy modules print when they load ("Loading model...").
    loaded = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    assert loaded.startswith("FORBIDDEN="), result.stdout
    assert loaded == "FORBIDDEN=", f"pure modules pull in: {loaded.removeprefix('FORBIDDEN=')}"
