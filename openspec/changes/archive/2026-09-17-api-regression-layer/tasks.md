## 1. Andamiaje de la capa

- [x] 1.1 Declarar el marcador `api` en `pyproject.toml`; verificar que `uv run pytest --markers` lo lista y que `--strict-markers` no protesta
- [x] 1.2 Crear `tests/api/conftest.py` con el marcado automático de la capa y un fixture de sesión que importe la aplicación una sola vez (D8); verificar con `uv run pytest tests/api --collect-only` que los tests quedan marcados como `api`
- [x] 1.3 Escribir `tests/api/dobles.py` con el constructor de guiones del grafo (D2): `ainvoke` devuelve el estado final, y `astream` emite tuplas `(mode, chunk)` con la forma real de `nodes.py`, incluidos el canal `custom` del redactor y las actualizaciones por nodo; verificar con un test mínimo que el endpoint de stream produce eventos SSE a partir de un guion
- [x] 1.4 Añadir al `conftest.py` el fixture que instala los dobles con `monkeypatch` sobre `src.api.routers.chat` y `src.api.routers.ingest`, y devuelve el cliente más el registro de llamadas (D1, D5, sin gestor de contexto); verificar que un test de humo obtiene 200 sin base de datos en marcha
- [x] 1.5 Escribir el test que falla si la capa abre una conexión a PostgreSQL (D5), vigilando `asyncpg.connect`; verificar que pasa con Docker parado y que falla si un test añade una conexión a propósito

## 2. Autenticación en el borde (`SEC-01`, `SEC-02`)

- [x] 2.1 Tests de 401: token firmado con otra clave, token sin `sub`, token sin `tenant_id` y petición sin cabecera; verificar además que el doble del grafo no se llamó en ninguno
- [x] 2.2 Test de `tenant_id` malformado (incluido el payload de inyección del hallazgo) → 401 y ningún 500; verificar que el valor no llega al doble del grafo
- [x] 2.3 Control positivo con `/auth/token` real: un token obtenido del endpoint entra y llega al grafo con el `tenant_id` del usuario, tipado como UUID; verificar que pasa
- [x] 2.4 Test en subproceso del arranque sin `JWT_SECRET_KEY` y con una clave de menos de 32 caracteres (D4); verificar que el mensaje explica la causa y que con una clave válida el import funciona

## 3. Detalle de los errores internos (`SEC-06`)

- [x] 3.1 Test de `POST /chat/`: el doble del grafo lanza una excepción con una ruta del servidor en el texto; verificar que el cliente recibe `Error interno (<id>)`, que la ruta no aparece y que el log trae la traza con ese mismo identificador una sola vez
- [x] 3.2 Test de `POST /chat/stream/`: la excepción ocurre durante el stream; verificar que el evento entregado lleva la clave `error` con el identificador y sin el texto de la excepción
- [x] 3.3 Test de `POST /ingest/`: `ingest_file` doblado lanza una excepción que nombra la ruta temporal; verificar el mensaje genérico y que la ruta no sale al cliente
- [x] 3.4 Tests de lo que sí debe conservarse: extensión no permitida (400 con su mensaje) y grafo sin respuesta final (500 con "El Grafo de Agentes no devolvió una respuesta final."); verificar que ninguno se convierte en el mensaje genérico

## 4. Objeto persistido en el caché (`BUG-01`)

- [x] 4.1 Test de stream con un guion cacheable: verificar que el objeto que recibe el doble de `save_semantic_cache` no contiene ningún mensaje de progreso y coincide con la respuesta estructurada, mientras que el texto emitido al cliente sí los lleva
- [x] 4.2 Test de que el doble del evaluador recibe también el texto limpio; verificar que se programó como tarea en segundo plano y con qué argumentos
- [x] 4.3 Test del camino sin caché: con historial en la petición, verificar que ni se consulta ni se guarda el caché (la política ya está cubierta en la capa 1; aquí se comprueba que el endpoint la respeta)

## 5. Caminos del stream (`BUG-09`)

- [x] 5.1 Tests con guion de supervisor que resuelve la petición (saludo, fuera de alcance y herramienta): verificar que el último evento contiene la respuesta y no solo las líneas de progreso
- [x] 5.2 Test con guion de redactor: verificar que el último evento contiene la respuesta completa una sola vez, sin duplicar el texto emitido token a token
- [x] 5.3 Test de acierto de caché en el stream: verificar que se emite un único evento con la respuesta cacheada y que el grafo no se llegó a ejecutar

## 6. Control negativo por hallazgo

- [x] 6.1 `SEC-01` y `SEC-02`: restaurar el comportamiento anterior (clave por defecto en `auth.py`; `tenant_id` como `str` en `User`), comprobar que falla al menos un test de esa sección y deshacer; anotar aquí cuál falló
- [x] 6.2 `SEC-06`: devolver `str(e)` en los tres puntos, uno a uno; comprobar que falla el test correspondiente y deshacer; anotar aquí cuál falló
- [x] 6.3 `BUG-01`: persistir el objeto del stream en lugar del limpio; comprobar que falla y deshacer; anotar aquí cuál falló
- [x] 6.4 `BUG-09`: no añadir la respuesta del supervisor al texto acumulado; comprobar que falla y deshacer; anotar aquí cuál falló

### Resultados del control negativo (2026-09-17)

Cada defecto se reintrodujo en el código, se ejecutó `tests/api` y se restauró con `git checkout` (árbol limpio al terminar).

| Hallazgo | Reintroducido | Tests que fallan |
|---|---|---|
| `SEC-01` | clave por defecto en `auth.py` | 1: la API no arranca sin clave utilizable |
| `SEC-01` | sin longitud mínima de la clave | 1: la API no arranca sin clave utilizable |
| `SEC-02` | `tenant_id` como `str` en `User` | 5: tenant malformado (4 casos) y el control positivo del token |
| `SEC-06` | `str(e)` al cliente en `POST /chat/` | 1: fallo interno en respuesta normal |
| `SEC-06` | `str(e)` en el evento de error del stream | 1: fallo interno durante el stream |
| `SEC-06` | `str(e)` al cliente en `POST /ingest/` | 1: fallo interno en la ingesta |
| `BUG-01` | persistir el objeto del stream, con el progreso | 1: lo que se guarda no lleva los mensajes de progreso |
| `BUG-01` | evaluar el texto acumulado en lugar del limpio | 1: el evaluador recibe la respuesta limpia |
| `BUG-09` | no añadir al stream la respuesta del supervisor | 6: los tres caminos del supervisor, más la no duplicación |

### Hallazgo nuevo encontrado al cerrar (2026-09-17)

La suite completa terminaba con código 134 en ~7 de cada 8 ejecuciones, **después** de que los 129 tests pasaran. El informe de macOS señala la telemetría de `onnxruntime` (llega con FlashRank): su hilo de eventos procesa una respuesta HTTP cuando el intérprete ya está cerrando y aborta el proceso. Solo se daba en la suite completa, la única que carga FlashRank al importar la aplicación. Mitigado en `tests/conftest.py` con `onnxruntime.disable_telemetry_events()` antes de que nada importe el re-ranker: 20 ejecuciones seguidas sin fallo. Queda catalogado como hallazgo aparte en la auditoría, con la decisión sobre producción pendiente del usuario.

## 7. Cierre

- [x] 7.1 Ejecutar `uv run pytest` completo dos veces seguidas; verificar que pasan, medir el tiempo total y comprobar que no quedan contenedores ni volúmenes de prueba
- [x] 7.2 Verificar que la capa de API pasa sola y sin Docker (`uv run pytest tests/api` con `docker` fuera del PATH) y que `uv run pytest tests/unit` sigue en el orden de 0,3 s
- [x] 7.3 Comprobar que la base de datos de desarrollo queda intacta: recuentos 22/128/4/3/0 y mismo volumen antes y después
- [x] 7.4 Anotar en `docs/AUDITORIA_TECNICA.md` que `SEC-01`, `SEC-02`, `SEC-06`, `BUG-01` y `BUG-09` pasan a tener regresión automática, con la tabla de controles negativos
- [x] 7.5 Commits en la rama `test/api-regression-layer`, uno por unidad de trabajo y con las mediciones en el cuerpo; verificar con `git status` que no queda nada sin commitear fuera de lo decidido
