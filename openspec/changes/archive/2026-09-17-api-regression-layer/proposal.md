## Why

La suite de regresión (`regression-test-suite`) dejó fuera el borde HTTP. Cinco correcciones siguen sin ningún test que las proteja, entre ellas los dos hallazgos 🔴 de la auditoría: `SEC-01` (token firmado con otra clave), `SEC-02` (`tenant_id` malformado en el token), `SEC-06` (el texto de la excepción llegaba al cliente), `BUG-01` (el caché guardaba la respuesta contaminada con los mensajes de progreso) y `BUG-09` (`/chat/stream/` no devolvía respuesta para saludos, temas fuera de alcance ni herramientas). Hoy su única prueba vive en los mensajes de commit y en la auditoría, así que reintroducir cualquiera de ellas no rompe nada.

## What Changes

- Tercera capa de la suite, `tests/api/`: la aplicación FastAPI completa con `TestClient`, y dobles en lugar del grafo y de los servicios de datos.
  - **Autenticación real, sin dobles:** los 401 de `SEC-01` y `SEC-02` se comprueban con el `get_current_user` de verdad.
  - **Dobles:** `agent_graph` (`ainvoke` y `astream`), `check_semantic_cache`, `save_semantic_cache`, `retrieve_user_facts`, `extract_and_save_facts` y `evaluate_rag_response`, sustituidos en el espacio de nombres de `src/api/routers/chat.py`. La capa no se conecta a Postgres ni llama a ningún LLM, y **no necesita Docker**.
- Regresiones cubiertas: 401 ante token con otra clave, sin `sub` o sin `tenant_id`, y ante `tenant_id` malformado (`SEC-01`, `SEC-02`); la API no arranca sin `JWT_SECRET_KEY` o con una demasiado corta (`SEC-01`); mensaje genérico con identificador ante un fallo interno, en los tres puntos, y mensajes escritos para el cliente que se conservan (`SEC-06`); el objeto que se manda a persistir en caché va limpio, mientras el que recibe el cliente lleva el progreso (`BUG-01`); el stream devuelve respuesta para saludos, temas fuera de alcance y herramientas (`BUG-09`).
- Marcador `api` y selección por directorio, como las otras capas. La capa entra en la ejecución por defecto de `uv run pytest`.
- Control negativo por hallazgo, como en el cambio anterior: cada defecto se reintroduce, se comprueba que falla al menos un test y se restaura.
- Estado de los cinco hallazgos en `docs/AUDITORIA_TECNICA.md`: todos están ya corregidos, así que lo que se anota es que pasan a tener regresión automática.

## Capabilities

### New Capabilities
_Ninguna._

### Modified Capabilities
- `regression-test-suite`: se añaden los requisitos de la capa de API (cómo se ejecuta y qué dobles usa) y los de las cinco regresiones del borde HTTP. Los requisitos existentes no cambian.

## Impact

- **Código de producción:** ninguno previsto. `agent_graph` y los servicios ya son nombres de módulo en `src/api/routers/chat.py`, así que se sustituyen desde el test. Si al implementarlo apareciera un punto que no se puede doblar sin tocar producción, se decide antes de cambiar nada.
- **Tests y configuración:** `tests/api/` (nuevo, con su `conftest.py` y sus dobles) y `pyproject.toml` (marcador `api`).
- **Tiempo de la suite:** la ejecución completa pasa de ~8 s a ~18 s, porque importar la aplicación carga el modelo de embeddings y el re-ranker (~10 s, una vez por ejecución). `uv run pytest tests/unit` sigue en ~0,3 s.
- **Documentación:** `docs/AUDITORIA_TECNICA.md`.
- **Fuera de alcance:** las evals de calidad y lo que declara el README sobre ellas; la ingesta de extremo a extremo (`SEC-04` ya tiene su test de capa 1); las mediciones de rendimiento y de Docker, que siguen siendo manuales; y la capa 2 de `SEC-07` (neutralizar `search_path` en la aplicación), que es una decisión aparte.
