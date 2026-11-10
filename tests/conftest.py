"""Common configuration for the suite. pytest loads this file before any test.

The environment is set here, before anything imports `src`: `src/services/db.py` reads
DATABASE_URL only once, at import time, and its default (and the one in the repository's
.env) is the development database. A test that imported db.py before this point would
leave the process connected to development without any visible error. Since load_dotenv()
does not overwrite existing variables, from here on the .env no longer affects what we set.
"""
import os
import secrets
from pathlib import Path

# Port of the disposable database of tests/db/. Never development's 5433.
TEST_DB_PORT = 5439
TEST_DB_DSN = f"postgresql://app_user:apppassword@127.0.0.1:{TEST_DB_PORT}/postgres"

os.environ["DATABASE_URL"] = TEST_DB_DSN
# Keys of their own for each run: the signing key is also passed to Compose, which seeds
# the disposable database with it. Neither matches the development .env. They are
# generated only once per process even if this module were imported twice
# (tests/db/conftest.py imports TEST_DB_PORT from here): changing them mid-session would
# leave the application's signature out of step with the database's.
if os.environ.get("_SANDBOX_TESTS_PID") != str(os.getpid()):
    os.environ["TENANT_SIGNING_KEY"] = secrets.token_hex(32)
    os.environ["JWT_SECRET_KEY"] = secrets.token_hex(32)
    os.environ["_SANDBOX_TESTS_PID"] = str(os.getpid())
# A single pool for the whole database layer; there is no need to reserve five connections.
os.environ["DB_POOL_MIN_SIZE"] = "1"

# onnxruntime's telemetry (it comes with FlashRank) starts a thread that processes HTTP
# responses. If one arrives when the interpreter is already shutting down, it aborts the
# process with code 134 ("recursive_mutex lock failed") after every test has passed. It
# is disabled here, before anything imports the re-ranker.
try:
    import onnxruntime

    onnxruntime.disable_telemetry_events()
except Exception:  # onnxruntime is a transitive dependency: if it is missing, there is nothing to disable
    pass

EVALS_DIR = Path(__file__).parent / "evals"


def pytest_addoption(parser):
    parser.addoption(
        "--run-evals", action="store_true", default=False,
        help="Also collect tests/evals/ (quality evaluations with an LLM judge).",
    )


def pytest_ignore_collect(collection_path, config):
    # Ignore them at collection rather than deselecting them with a marker: collecting
    # a module makes pytest import it, and tests/evals/ imports deepeval and the services.
    if not config.getoption("--run-evals") and collection_path.is_relative_to(EVALS_DIR):
        return True
    return None
