## Why

El repositorio no tiene ningún test ejecutable (`BUG-07`). La única suite, `tests/test_rag.py`, falla con un `TypeError` antes de evaluar nada. Aunque se corrigiera, necesitaría un juez de OpenAI que no está configurado y preguntaría por un documento que no está en el corpus. Mientras tanto, la remediación de la auditoría ha cerrado más de veinte hallazgos, y cada corrección se verificó con un control negativo desde scripts efímeros que ya no existen: nada impide que esos defectos vuelvan. Esa red de regresión hace falta antes de seguir tocando el código (`HYG-05`, capas 2 y 3 de `SEC-07`, API con dobles).

## What Changes

- Nueva suite de regresión en `tests/`, organizada en dos capas:
  - **Capa 1, lógica pura:** sin base de datos, sin LLM, sin `.env` y sin cargar modelos. Cubre la política de caché (`BUG-02`, `BUG-06`, `BUG-10`), la ventana de recuperación, el agotamiento y la ruta del revisor (`BUG-05`), el formateo del historial (`BUG-03`), el saneado del nombre de archivo (`SEC-04`), la firma del tenant (`SEC-05`) y los límites de las puntuaciones del evaluador (`DOC-02`).
  - **Capa 2, Postgres real y desechable:** una base levantada por la propia suite desde volumen vacío. Cubre el aislamiento con contexto firmado (`SEC-05`), la consulta de GraphRAG ante un payload de inyección (`SEC-03`), que el tenant no sobreviva en el pool (`PERF-01`), los privilegios de `app_user` (`HYG-07`, `SEC-07`) y el arranque desde cero (`BUG-04`).
- Se extraen funciones puras de módulos que, al importarse, cargan modelos o crean clientes. Se mueven sin cambiar su comportamiento, y los módulos originales las importan del nuevo sitio:
  - la política de caché, desde `src/api/routers/chat.py`;
  - `retrieval_window`, la decisión de agotamiento (hoy en línea en `researcher_node`) y `route_reviewer`, desde `src/services/agent_graph/`;
  - el saneado del nombre de origen (hoy en línea en `ingest_endpoint`);
  - el modelo `RAGEvaluation`, desde `src/services/evaluator.py`.
- Configuración de pytest: recolección limitada a `tests/`, `pytest-asyncio` y marcadores para seleccionar capas. Sin Docker, la capa 2 **falla**, no se salta.
- `pytest` y `pytest-asyncio` pasan a dependencias de desarrollo.
- `tests/test_rag.py` no se arregla aquí: queda marcado como eval y excluido de la ejecución por defecto, hasta el cambio de evals.
- La ficha de `BUG-07` en `docs/AUDITORIA_TECNICA.md` recibe su línea de estado, con la corrección de que el parche mínimo propuesto ya no aplica.

## Capabilities

### New Capabilities
- `regression-test-suite`: qué debe demostrar la suite de regresión, cómo se ejecuta cada capa y qué garantías da sobre la base de datos de desarrollo y sobre el entorno.

### Modified Capabilities
_Ninguna: no hay specs previas y las extracciones no cambian el comportamiento observable de la aplicación._

## Impact

- **Código de producción (solo movimientos):** `src/api/routers/chat.py`, `src/api/routers/ingest.py`, `src/services/agent_graph/nodes.py`, `src/services/agent_graph/graph.py`, `src/services/evaluator.py`, más los módulos nuevos que reciben lo extraído.
- **Tests y configuración:** `tests/` (suite nueva, `conftest.py`, fixtures) y `pyproject.toml` (configuración de pytest, grupo de desarrollo).
- **Infraestructura de pruebas:** Docker pasa a ser requisito para la suite completa. La capa 2 usa un proyecto Compose propio, con su puerto y su volumen, que borra por nombre exacto al terminar. Nunca toca la base de desarrollo ni su volumen `ai_engineer_sandbox_pgdata`.
- **Documentación:** `docs/AUDITORIA_TECNICA.md` (estado de `BUG-07`). El README no se toca aquí: su afirmación de *"Evals deterministas (DeepEval)"* corresponde al cambio de evals.
- **Fuera de alcance:** la capa de API con dobles (`SEC-01`, `SEC-02` en el borde, `SEC-06`, `BUG-01`, `BUG-09`), que será el siguiente cambio; las evals de calidad con juez LLM; las mediciones de rendimiento y las verificaciones de Docker (`PERF-02` a `PERF-04`, `DOC-01`, `HYG-06`, `HYG-08`, `DOC-03`), que siguen siendo manuales; y los scripts sueltos de la raíz (`HYG-02`).
