## Context

Ver `proposal.md` (Why) y la spec `regression-test-suite` para los requisitos. Lo que condiciona el diseño, leído del código actual:

- **Todo lo que hay que doblar son nombres de módulo en `src/api/routers/chat.py`**: `agent_graph` (global creado con `build_graph()` al importar), `check_semantic_cache`, `save_semantic_cache`, `retrieve_user_facts`, `extract_and_save_facts` y `evaluate_rag_response`. En `src/api/routers/ingest.py`, `ingest_file`. Sustituirlos desde el test no exige tocar producción.
- **El stream consume dos canales**: `agent_graph.astream(state, stream_mode=["updates", "custom"])` entrega tuplas `(mode, chunk)`. Con `custom`, `chunk` es `{"delta": str}`; con `updates`, `{nombre_nodo: actualización_de_estado}`. El endpoint distingue el nodo `generator` del resto: la respuesta del supervisor la añade al texto acumulado, y la del redactor no, porque ya se emitió token a token (`BUG-09`).
- **`BUG-01` es exactamente la diferencia entre dos objetos**: `final_dict` (limpio, el que se persiste y el que va al evaluador) y `stream_dict` (con el progreso, el que ve el cliente).
- **La autenticación no necesita dobles**: `get_current_user` decodifica con `SECRET_KEY`, leída al importar `src/api/auth.py`, y construye `User`, donde `tenant_id: uuid.UUID` rechaza un valor malformado (`SEC-02`).
- **`tests/conftest.py` ya fija `JWT_SECRET_KEY` aleatoria por ejecución** antes de importar `src`, así que los tests pueden firmar tokens con la misma clave que el servidor.
- **`TestClient` entrega los eventos SSE de golpe**: sirve para contar eventos y afirmar sobre su contenido, no para medir latencia.
- **El `lifespan` de la aplicación abre el pool al arrancar**, y captura el fallo si Postgres no está. `TestClient` solo ejecuta el `lifespan` cuando se usa como gestor de contexto.
- `starlette.testclient` y `httpx` 0.28.1 ya están instalados; no hace falta declarar nada nuevo.

## Goals / Non-Goals

**Goals:**
- Fijar el contrato del borde HTTP para las cinco correcciones, sin red, sin base de datos y sin Docker.
- Que cada test afirme sobre lo que ve el cliente o sobre lo que reciben los servicios, no sobre cómo está escrito el endpoint.
- No tocar código de producción.

**Non-Goals:**
- Sustituir la verificación de extremo a extremo: con el grafo doblado, estos tests no dicen nada sobre la calidad de las respuestas ni sobre la integración real.
- Medir latencia o comportamiento incremental del stream (`DOC-01`), que necesita uvicorn de verdad.
- Cubrir la ingesta completa: aquí solo se ejercita su borde HTTP para `SEC-06`.

## Decisions

### D1. Dobles instalados con `monkeypatch` sobre el módulo del router
Un fixture sustituye cada nombre en `src.api.routers.chat` (y `ingest_file` en `src.api.routers.ingest`) por un doble que registra las llamadas y devuelve lo que el test configure. `monkeypatch` restaura al terminar cada test.
- *Alternativa descartada: `app.dependency_overrides`.* Solo cubre dependencias de FastAPI, y ni el grafo ni los servicios lo son.
- *Alternativa descartada: inyectar el grafo como dependencia en producción.* Cambiaría el código para hacerlo testeable, y la propuesta es no tocarlo.

### D2. Un único constructor de guiones del grafo
Los dobles de `ainvoke` y `astream` se construyen en un solo módulo de ayuda (`tests/api/dobles.py`) a partir de un "guion" declarativo: qué nodos emiten, con qué actualización de estado, y qué texto emite el redactor por el canal `custom`. Así la forma de los datos del grafo está escrita una vez, y los tests describen el caso, no el protocolo.
- *Riesgo asumido, ver más abajo:* si el grafo real cambia la forma de lo que emite, el doble puede quedar desactualizado sin que nada falle.

### D3. Tokens firmados en el test con la clave real del proceso
Los tests generan tokens con `jwt.encode` y la `JWT_SECRET_KEY` del entorno que fija `tests/conftest.py`. Para `SEC-01`, un token firmado con otra clave; para `SEC-02`, un `tenant_id` no-UUID (incluido un fragmento de SQL, que es el payload del hallazgo).
- *Alternativa descartada: usar `/auth/token`.* Sirve como control positivo, pero no permite construir los tokens inválidos que son el objeto de estos tests. Se usa además un caso por el endpoint real, para no depender solo de tokens fabricados.

### D4. El arranque sin clave se comprueba en un subproceso
`SEC-01` incluye que el proceso no arranque sin `JWT_SECRET_KEY` o con una corta. Como la clave se lee al importar `src/api/auth.py`, se comprueba lanzando un subproceso que importa el módulo con el entorno modificado y esperando un fallo con mensaje explicativo. Es el mismo patrón del guardián de pureza de la capa 1.

### D5. `TestClient` sin gestor de contexto
El cliente se crea como `TestClient(app)` sin `with`, de modo que no se ejecuta el `lifespan` y la capa no intenta abrir el pool de Postgres. Un test aparte comprueba explícitamente que durante la capa no se abre ninguna conexión, monitorizando `asyncpg.connect`.
- *Alternativa descartada: usar `with` y dejar que el pool falle.* Funciona porque el error se captura, pero deja a la capa dependiendo de que ese `try` siga ahí.

### D6. Afirmaciones sobre los eventos SSE, nunca sobre tiempos
El stream se lee con `client.post(...)` y los eventos se extraen de las líneas `data: `. Se afirma sobre el número de eventos, el último evento y la presencia o ausencia de textos. Nada de latencias (ver Context).

### D7. Tareas en segundo plano
`TestClient` ejecuta las tareas de `BackgroundTasks` antes de devolver el control, así que los dobles de memoria y evaluador registran sus llamadas y el test puede afirmar sobre lo que recibieron, que es como se comprueba la mitad de `BUG-01`.

### D8. Ubicación y selección
`tests/api/`, con marcador `api` puesto automáticamente por su `conftest.py`, igual que `db` en la capa 2. Entra en la ejecución por defecto. La aplicación se importa una vez por sesión (fixture de sesión), porque ese import cuesta ~10 s.

## Risks / Trade-offs

- **[El doble del grafo se desincroniza de la forma real]** → Es el riesgo principal: un cambio en lo que emiten los nodos dejaría los tests en verde sobre un protocolo que ya no existe. Se acota concentrando la forma en `tests/api/dobles.py` y derivándola de `nodes.py`, y se compensa con la verificación manual de extremo a extremo, que sigue siendo obligatoria en cada hallazgo. No se elimina.
- **[Los dobles atan los tests a nombres internos]** → Si el grafo deja de ser un global de `chat.py`, hay que tocar el fixture, no cada test: por eso los dobles se instalan en un solo sitio.
- **[Importar la aplicación cuesta ~10 s]** → La suite completa pasa de ~8 s a ~18 s. Para iterar sigue estando `uv run pytest tests/unit`.
- **[Un test podría abrir conexión sin querer]** → Lo detecta el test de D5, que falla si algo llama a `asyncpg.connect` durante la capa.
- **[`SEC-06` depende de que el log recoja la traza]** → Se comprueba capturando el log con el fixture `caplog` y exigiendo que el identificador del cliente aparezca exactamente una vez, junto al texto que no debe salir de ahí.

## Migration Plan

No hay despliegue. Orden: fixture con los dobles y el cliente → autenticación (`SEC-01`, `SEC-02`) → errores internos (`SEC-06`) → objeto persistido (`BUG-01`) → caminos del stream (`BUG-09`) → control negativo por hallazgo → estado en la auditoría. Deshacer es revertir la rama; no hay cambios en producción que revertir.

## Open Questions

- Si conviene además un test que compruebe que el `lifespan` abre el pool al arrancar. Es comportamiento de arranque, no una regresión de la auditoría, y no cambia ni la spec ni las tareas.
