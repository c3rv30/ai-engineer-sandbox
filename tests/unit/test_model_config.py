"""DOC-07: the LLM model is named in one place, and ANTHROPIC_MODEL can change it.

Before, the same identifier was written out in seven calls, so a model change took seven
coordinated edits. The source is read as text: importing the services would load the
models and the LLM clients, which this layer does not do.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODEL_ID = re.compile(r"claude-(haiku|sonnet|opus)-[0-9]")


def test_the_model_id_is_written_only_in_the_config():
    where = [str(path.relative_to(REPO)) for path in sorted((REPO / "src").rglob("*.py"))
             if MODEL_ID.search(path.read_text())]
    assert where == ["src/config.py"]


def test_every_llm_call_uses_the_configured_model():
    calls = [(str(path.relative_to(REPO)), line.strip())
             for path in sorted((REPO / "src").rglob("*.py"))
             for line in path.read_text().splitlines()
             if re.match(r"\s*model=", line)]
    assert len(calls) == 7
    assert all(line == "model=ANTHROPIC_MODEL," for _, line in calls), calls


def test_the_environment_can_change_the_model():
    # In a new process: the value is read once, when src.config is first imported.
    env = {**os.environ, "ANTHROPIC_MODEL": "claude-test-model"}
    result = subprocess.run([sys.executable, "-c", "import src.config as c; print(c.ANTHROPIC_MODEL)"],
                            cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
    assert result.stdout.strip() == "claude-test-model", result.stderr
