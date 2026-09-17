## Context

Ver `proposal.md` (Why) y la spec `regression-test-suite` para los requisitos. Este documento recoge solo las restricciones del código actual que condicionan el diseño.

- **Importar la lógica pura cuesta ~10 s.** Medido el 2026-09-16: `src.services.agent_graph.nodes` tarda 8,9 s y `src.api.routers.chat` 9,9 s, porque arrastran `sentence_transformers`, `flashrank`, `anthropic`, `langgraph` y `asyncpg`. `src.services.history` y `src.models.requests` tardan ≤ 0,1 s. `graph.py` importa `nodes.py`, así que `route_reviewer` también paga ese coste.
- **Hay lógica pura escrita en línea.** La decisión de agotamiento de `BUG-05` está dentro de `researcher_node`, y el saneado del nombre de `SEC-04`, dentro de `ingest_endpoint`.
- **`src/services/db.py` fija la base al importarse.** `DB_DSN` se lee una vez, con `load_dotenv()` y un valor por defecto que apunta a la base de desarrollo (`localhost:5433`). Un test que importe `db.py` antes de que el entorno apunte a la base de pruebas deja el proceso conectado a desarrollo, y ningún error lo delata.
- **El pool es uno por event loop** (`PERF-01`), con `DB_POOL_MIN_SIZE=5` por defecto. Por defecto, pytest-asyncio da un loop nuevo a cada test.
- **Los paquetes `src/api/`, `src/api/routers/` y `src/services/agent_graph/` tienen `__init__.py` vacíos**, y `src/`, `src/services/` y `src/models/` no tienen. Un módulo nuevo dentro de cualquiera de ellos no arrastra importaciones por el paquete.
- **`tests/test_rag.py` importa `deepeval` y los servicios a nivel de módulo.** Deseleccionarlo con un marcador no basta, porque pytest lo importa al recogerlo.
- El proyecto usa `uv` (`uv.lock`, README), y `pytest` figura hoy entre las dependencias de producción.

## Goals / Non-Goals

**Goals:**
- Que el aislamiento entre la capa pura y la de base de datos sea estructural, no una convención: se garantiza con directorios, un test de importación y un guardián del DSN.
- Que la capa de base de datos no pueda alcanzar la base de desarrollo por accidente, ni por el orden de importación ni por el `.env`.
- Mover lógica sin cambiar su comportamiento, con los tests nuevos como prueba.

**Non-Goals:**
- Resolver `HYG-05`. Los módulos puros simplemente no crean clientes, y los servicios siguen como están.
- Paralelizar la suite, medir cobertura o montar integración continua.
- Automatizar el control negativo (mutation testing). Se hace a mano al escribir cada test (ver D8).

## Decisions

### D1. Capas por directorio: `tests/unit/`, `tests/db/` y `tests/evals/`
La capa se decide por el directorio, y un `conftest.py` marca automáticamente como `db` todo lo que hay en `tests/db/`. La capa pura se ejecuta con `uv run pytest tests/unit`, y la suite completa con `uv run pytest`.
- *Alternativa descartada: solo marcadores (`-m "not db"`).* Aun deseleccionados, pytest importaría los módulos de `tests/db/`, y bastaría una importación a nivel de módulo para cargar modelos o fijar el DSN. El directorio lo evita sin depender de disciplina.

### D2. Destino de las funciones extraídas
| Lógica | Módulo nuevo | Lo importa desde ahí |
|---|---|---|
| `CACHEABLE_INTENTS`, `MIN_CACHE_CONFIDENCE`, `is_cacheable`, `uses_default_retrieval`, `is_cache_eligible` | `src/services/cache_policy.py` | `src/api/routers/chat.py` |
| `retrieval_window`, decisión de agotamiento (función nueva con la expresión que hoy está en línea), `route_supervisor`, `route_reviewer` | `src/services/agent_graph/routing.py` | `nodes.py`, `graph.py` |
| Saneado del nombre de origen | `src/services/filenames.py` | `src/api/routers/ingest.py` |
| `RAGEvaluation` | `src/models/evaluation.py` | `src/services/evaluator.py` |

Los módulos nuevos solo pueden importar de la biblioteca estándar, `pydantic` y `src.models.*`. Los nombres públicos se mantienen, y los módulos originales los reexportan importándolos, así que nada que ya los use se rompe.
- *Alternativa descartada: importar perezosamente dentro de los módulos actuales.* Obligaría a tocar muchas más líneas y dejaría las funciones puras en módulos pesados.
- *Alternativa descartada: `src/api/policies.py` para la política de caché.* Esa política no es del borde HTTP: el día que otro punto de entrada use el caché, la necesitará sin FastAPI.

### D3. Test guardián de la pureza de la capa 1
Un test de `tests/unit/` importa todos los módulos puros en un subproceso limpio y comprueba que `sys.modules` no contiene `sentence_transformers`, `flashrank`, `anthropic` ni `langgraph`. Así, el escenario *Sin carga de modelos* deja de depender de que nadie añada una importación pesada.
- *Alternativa descartada: medir el tiempo de importación.* Es frágil e indirecto.

### D4. Ciclo de vida de la base desechable
Un fixture de sesión en `tests/db/conftest.py`:
1. Usa el proyecto Compose de nombre fijo `sandbox_tests`, con `--project-directory` en el repositorio y un override generado en un directorio temporal: puerto `127.0.0.1:5439`, `restart` anulado y el volumen del compose del repositorio (que resulta en `sandbox_tests_pgdata`).
2. **Antes de levantar**, elimina los restos de una ejecución interrumpida: `down` del proyecto `sandbox_tests` y borrado del volumen `sandbox_tests_pgdata`, por nombre exacto.
3. `up --wait`. Si falla (sin Docker, puerto ocupado, script de inicialización roto), llama a `pytest.fail` con la salida de Compose. Nunca `skip`.
4. En el finalizador, pase lo que pase: `down` y borrado del volumen por nombre exacto, comprobando antes que el volumen pertenece al proyecto `sandbox_tests`.

El nombre fijo impide dos ejecuciones simultáneas, pero garantiza que una ejecución matada no deja volúmenes huérfanos: la siguiente los limpia.
- *Alternativa descartada: nombre aleatorio por ejecución.* Permite paralelismo, pero una ejecución matada deja un volumen que nadie reconoce, y para limpiarlo habría que borrar por prefijo, que es justo el patrón de riesgo que evita tu memoria de verificación.
- *Alternativa descartada: testcontainers.* Añade una dependencia y no reutiliza `docker-compose.yml` ni los scripts `sql/`, que son lo que `BUG-04` debe demostrar.

### D5. El entorno se fija antes de cualquier importación de `src`
`tests/conftest.py` (el raíz, que pytest carga antes que ningún test) fija en `os.environ`:
- `DATABASE_URL=postgresql://app_user:apppassword@127.0.0.1:5439/postgres`;
- `TENANT_SIGNING_KEY`, generada aleatoriamente para la ejecución y pasada también a Compose, que antepone el entorno al `.env`;
- `JWT_SECRET_KEY`, aleatoria;
- `DB_POOL_MIN_SIZE=1`.

Como `load_dotenv()` no sobrescribe variables existentes, el `.env` del repositorio deja de influir. Además, el fixture de sesión de la base **comprueba que `src.services.db.DB_DSN` apunta al puerto 5439** y aborta la sesión si no es así (por ejemplo, si algo importó `db.py` antes que el conftest).
- *Alternativa descartada: parchear `DB_DSN` en el fixture.* Deja una ventana en la que un import temprano ya conectó con desarrollo, y esconde el problema en lugar de detectarlo.

### D6. Pool y event loop en la capa 2
Los tests async de `tests/db/` comparten un único event loop de sesión (pytest-asyncio con `loop_scope="session"`), y el fixture de sesión cierra el pool con `close_pool()` al terminar. Así, `get_pool()` crea un solo pool para toda la capa, igual que en producción, y el test de `PERF-01` ejercita la reutilización real de conexiones.
- *Alternativa descartada: loop por test.* Crearía un pool por test sin cerrar los anteriores, y agotaría conexiones de forma parecida al síntoma original de `PERF-01`.

### D7. Datos de prueba
Cada test siembra lo que necesita como superusuario (`postgres`, que elude RLS) en la base desechable, con tenants propios (`aaaaaaaa-…` y `bbbbbbbb-…`) y valores inventados imposibles de adivinar, y comprueba siempre como `app_user` a través del código real (`tenant_connection`, `retrieve_subgraph`). La base se recrea en cada ejecución, así que no hace falta purgar entre ejecuciones. Dentro de una ejecución, cada test usa sus propios valores para no depender del orden.

### D8. Control negativo al escribir cada test
Para cada hallazgo se reintroduce temporalmente el comportamiento anterior. Según el caso, se restaura la versión previa de la función con `git show <commit>^:<ruta>`, o se ejecuta el SQL anterior (`GRANT ALL ON DATABASE`, `ALTER DEFAULT PRIVILEGES`, política sin firma) en la base desechable. Se comprueba que el test falla, se deshace el cambio y se anota el resultado en `tasks.md` y en el mensaje del commit. No queda ninguna herramienta permanente.

### D9. Dependencias y configuración de pytest
- `pyproject.toml`: `pytest` sale de `dependencies` y entra, junto a `pytest-asyncio`, en `[dependency-groups] dev`. `deepeval` se queda donde está hasta el cambio de evals.
- `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, marcadores `db` y `eval` declarados con `--strict-markers`, y `asyncio_default_fixture_loop_scope` explícito.
- `tests/test_rag.py` se mueve a `tests/evals/`. `tests/conftest.py` añade `tests/evals/` a `collect_ignore_glob` salvo que se pase `--run-evals`. Así no se importa `deepeval` en la ejecución por defecto.

## Risks / Trade-offs

- **[Un movimiento cambia el comportamiento sin que se note]** → Los tests de capa 1 se escriben primero contra la función en su sitio actual, con la importación pesada, y se ejecutan de nuevo tras moverla: mismos resultados. Después, las importaciones antiguas siguen resolviendo, y lo comprueba un arranque real de la API con una petición.
- **[El puerto 5439 está ocupado]** → `up --wait` falla y la sesión termina en `pytest.fail` con la salida de Compose, que nombra el puerto (ver Open Questions).
- **[Un `kill -9` deja la base de pruebas en marcha]** → Se limpia al inicio de la siguiente ejecución (D4, paso 2). Nunca queda afectado nada fuera del proyecto `sandbox_tests`.
- **[La capa 2 añade ~15 s por ejecución]** → Asumido: la base recién creada es el objetivo. Para iterar rápido está `tests/unit`.
- **[Docker pasa a ser requisito para la suite completa]** → Decisión confirmada: fallar es preferible a una capa saltada en silencio.
- **[`graphrag.py` crea un cliente de Anthropic sin clave al importarse (`HYG-05`)]** → No afecta a `retrieve_subgraph`, que no llama al LLM. Si una versión futura del SDK valida la clave al construir el cliente, el test lo mostrará como error de importación y se tratará con `HYG-05`.

## Migration Plan

No hay despliegue. Orden de trabajo pensado para que cada paso sea verificable por sí solo (detalle en `tasks.md`): configuración de pytest y dependencias → tests de capa 1 contra el código actual → extracciones, una por hallazgo, con los tests en verde antes y después → guardián de pureza → fixture de base desechable → tests de capa 2 → control negativo de cada hallazgo → estado en la auditoría. Deshacer es revertir los commits: las extracciones son movimientos con reexportación.

## Open Questions

- Si el puerto de la base de pruebas se hace configurable desde el principio o solo cuando choque con algo. No cambia ni la spec ni las tareas.
