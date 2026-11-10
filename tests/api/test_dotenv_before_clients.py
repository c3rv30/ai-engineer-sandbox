"""HYG-05: every service loads .env before it builds its Anthropic client.

Each module is imported first, alone, in a new process: that is how a script or a
worker uses it, and the order the API happens to import things in cannot hide the
defect there. The environment has no ANTHROPIC_API_KEY and load_dotenv is doubled to
provide one, so the test needs no .env and makes no LLM call: a client built before
.env was loaded is left without a key, and the first call fails with "Could not resolve
authentication method".

It lives in this layer because the services import anthropic and instructor.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
KEY = "key-from-dotenv"

PROBE = """
import json, os, sys
import dotenv

def load_dotenv(*args, **kwargs):  # what the .env would provide
    os.environ.setdefault("ANTHROPIC_API_KEY", {key!r})
    return True

dotenv.load_dotenv = load_dotenv

from anthropic import AsyncAnthropic
module = __import__({module!r}, fromlist=["_"])
keys = []
for value in vars(module).values():
    inner = getattr(value, "client", None)
    for candidate in (value, inner):
        if isinstance(candidate, AsyncAnthropic):
            keys.append(candidate.api_key)
print(json.dumps(keys))
"""


@pytest.mark.parametrize("module", [
    "src.services.router",
    "src.services.extractor",
    "src.services.evaluator",
    "src.services.graphrag",
    "src.services.memory",
])
def test_the_client_gets_the_key_from_dotenv(module):
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run([sys.executable, "-c", PROBE.format(key=KEY, module=module)],
                            cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    keys = json.loads(result.stdout.strip().splitlines()[-1])
    assert keys, f"{module} has no module-level Anthropic client"
    assert keys == [KEY] * len(keys)
