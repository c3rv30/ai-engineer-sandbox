"""Configuración común de la suite. pytest carga este archivo antes que cualquier test.

El entorno se fija aquí, antes de que nada importe `src`: `src/services/db.py` lee
DATABASE_URL una sola vez al importarse, y su valor por defecto —y el del .env del
repositorio— es la base de desarrollo. Un test que importara db.py antes de este punto
dejaría el proceso conectado a desarrollo sin ningún error visible. Como load_dotenv()
no sobrescribe variables existentes, a partir de aquí el .env ya no influye en lo que
fijamos.
"""
import os
import secrets
from pathlib import Path

# Puerto de la base desechable de tests/db/. Nunca el 5433 de desarrollo.
TEST_DB_PORT = 5439
TEST_DB_DSN = f"postgresql://app_user:apppassword@127.0.0.1:{TEST_DB_PORT}/postgres"

os.environ["DATABASE_URL"] = TEST_DB_DSN
# Claves propias de cada ejecución: la de firma se pasa también a Compose, que siembra
# con ella la base desechable. Ninguna coincide con las del .env de desarrollo. Se
# generan una sola vez por proceso aunque este módulo llegara a importarse dos veces
# (tests/db/conftest.py importa TEST_DB_PORT de aquí): cambiarlas a mitad de sesión
# dejaría la firma de la aplicación sin cuadrar con la de la base.
if os.environ.get("_SANDBOX_TESTS_PID") != str(os.getpid()):
    os.environ["TENANT_SIGNING_KEY"] = secrets.token_hex(32)
    os.environ["JWT_SECRET_KEY"] = secrets.token_hex(32)
    os.environ["_SANDBOX_TESTS_PID"] = str(os.getpid())
# Un solo pool para toda la capa de base de datos; no hace falta reservar cinco conexiones.
os.environ["DB_POOL_MIN_SIZE"] = "1"

# La telemetría de onnxruntime (llega con FlashRank) lanza un hilo que procesa
# respuestas HTTP. Si alguna llega cuando el intérprete ya está cerrando, aborta el
# proceso con código 134 ("recursive_mutex lock failed") después de que todos los tests
# hayan pasado. Se desactiva aquí, antes de que nada importe el re-ranker.
try:
    import onnxruntime

    onnxruntime.disable_telemetry_events()
except Exception:  # onnxruntime es una dependencia transitiva: si no está, no hay nada que desactivar
    pass

EVALS_DIR = Path(__file__).parent / "evals"


def pytest_addoption(parser):
    parser.addoption(
        "--run-evals", action="store_true", default=False,
        help="Recoge también tests/evals/ (evaluaciones de calidad con juez LLM).",
    )


def pytest_ignore_collect(collection_path, config):
    # Ignorarlos en la recolección, no deseleccionarlos con un marcador: al recoger un
    # módulo, pytest lo importa, y tests/evals/ importa deepeval y los servicios.
    if not config.getoption("--run-evals") and collection_path.is_relative_to(EVALS_DIR):
        return True
    return None
