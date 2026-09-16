# 🔎 Auditoría Técnica: Divergencias, Defectos y Deuda

> **Fecha:** 2026-09-10
> **Rama auditada:** `develop` (commit base `638ccee`, con `pyproject.toml` y `uv.lock` modificados sin commitear)
> **Entorno verificado:** Python 3.14.0 · `anthropic` 1.4.0 · `instructor` 1.16.0 · `langgraph` 1.2.11 · `pyjwt` 2.13.0 · `numpy` 2.5.2

## Alcance y método

Se auditó la totalidad del repositorio:

| Superficie | Volumen | Cobertura |
|---|---|---|
| Documentación | 11 archivos (`README.md`, `CONTEXT.md`, `ARCHITECTURE.md`, 8 en `docs/`) | Lectura completa, incluidos `PAPER.md` (478 l.) y `PAPER_EN.md` (496 l.) |
| Código fuente | 24 archivos, 1.694 líneas en `src/` | Lectura completa |
| Esquema de datos | 7 scripts en `sql/` | Lectura completa |
| Build e infraestructura | `pyproject.toml`, `uv.lock`, `docker-compose.yml`, `.env.example`, `.gitignore` | Lectura completa |
| Tests y scripts sueltos | `tests/test_rag.py`, `src/pipeline.py`, 6 scripts de raíz | Lectura completa |

**Método.** Cada afirmación de la documentación se contrastó contra el código que la implementa. Cada hallazgo incluye: ubicación exacta (`archivo:línea`), el extracto literal del código, un comando de verificación reproducible y un parche propuesto. No se ejecutó el sistema —no se levantó Postgres ni se consumió la API de Anthropic—; toda la evidencia es estática y verificable con `grep`, `cat` y lectura de fuente.

**Relación con la documentación existente.** [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) es un post-mortem de seis problemas ya resueltos. [`ROADMAP_FASE_5_ESCALABILIDAD.md`](ROADMAP_FASE_5_ESCALABILIDAD.md) planifica cinco epics futuros. `PAPER_PLAN.md` §5 lista seis limitaciones conocidas y asumidas. **Este documento cubre el hueco entre los tres**: lo que está roto o divergente *ahora*, no resuelto y no planificado.

## Valoración general

El proyecto es arquitectónicamente sólido. El grafo de LangGraph está bien descompuesto, el two-stage retrieval está correctamente implementado (RRF con `k=60` fusionando HNSW y FTS, seguido de cross-encoder), el semantic chunking estadístico es real y matemáticamente correcto, y las políticas RLS están bien escritas. La formalización del `PAPER.md` es rigurosa y en su mayor parte fiel.

El valor de esta auditoría no está en cuestionar el diseño sino en registrar tres cosas:

1. **La migración a la Fase 4 dejó código huérfano y documentación desactualizada.** La adopción de LangGraph reemplazó el pipeline lineal pero varias piezas del anterior siguen documentadas como vigentes (`DOC-01`, `BUG-06`) y otras quedaron desconectadas (`BUG-03`).
2. **Los papers afirman propiedades verificables que el código no cumple.** En un repositorio de portafolio esto tiene un coste específico: quien contraste el paper con el fuente encontrará la diferencia (`DOC-02`, `PERF-01`).
3. **El aislamiento multi-tenant —argumento central del proyecto— es anulable con dos líneas de código.** Las políticas RLS funcionan; la entrada al sistema es falsificable (`SEC-01`, `SEC-02`).

---

## 1. Resumen Ejecutivo

| Categoría | 🔴 Crítica | 🟠 Alta | 🟡 Media | ⚪ Baja | Total |
|---|:---:|:---:|:---:|:---:|:---:|
| Divergencias doc ↔ código | — | 3 | 4 | 1 | **8** |
| Defectos funcionales | — | 5 | 3 | — | **8** |
| Seguridad | 2 | 1 | 1 | — | **4** |
| Rendimiento | — | 2 | 2 | — | **4** |
| Higiene del repositorio | — | — | 2 | 2 | **4** |
| **Total** | **2** | **11** | **12** | **3** | **28** |

> **Posteriores a la foto.** No se suman a este recuento, que es el estado del 2026-09-10. Todos aparecieron al verificar correcciones contra el sistema real y están en el índice (§2) y en la tabla de remediación:
> - `BUG-09` (🟠), el 2026-09-13, al reescribir el bucle de streaming para `DOC-01`.
> - `SEC-05` (🟠), `SEC-06` (🟡), `BUG-10` (🟠), `HYG-05` (🟡) y `HYG-06` (⚪), el 2026-09-14.
> - `HYG-07` (🟡), el 2026-09-15, al implementar el parche de `SEC-05`.
> - `HYG-08` (🟠), el 2026-09-16, al revisar el estado de Docker.

### Criterios de severidad

| Nivel | Definición aplicada |
|---|---|
| 🔴 **Crítica** | Permite a un atacante leer o destruir datos de otro tenant. Bloqueante para cualquier despliegue. |
| 🟠 **Alta** | Rompe funcionalidad anunciada, corrompe datos persistidos, o degrada el sistema de forma medible bajo carga normal. |
| 🟡 **Media** | Divergencia verificable entre documentación y código, o defecto con impacto acotado y sin corrupción. |
| ⚪ **Baja** | Deuda cosmética o de mantenimiento sin impacto funcional. |

### Los cinco hallazgos que hay que atender primero

| # | ID | Por qué primero |
|:---:|---|---|
| 1 | `SEC-01` | El `SECRET_KEY` del JWT está hardcodeado y versionado. HS256 es simétrico: quien lee el repo puede firmar tokens con cualquier `tenant_id`. Anula todo el modelo de aislamiento. **5 minutos de corrección.** |
| 2 | `SEC-02` | `tenant_id` se interpola por f-string en `SET app.current_tenant` sin validarse. Encadenado con `SEC-01`, es inyección SQL con privilegios `ALL` sobre la base. **5 minutos de corrección.** |
| 3 | `BUG-01` | El caché semántico persiste la respuesta contaminada con los mensajes de progreso del stream. Corrompe datos de forma acumulativa: cada hit sirve una traza de ejecución falsa. |
| 4 | `BUG-03` | El historial conversacional nunca llega al grafo. La resolución de correferencias está escrita, probada y es inalcanzable. Reconectarla es propagar un campo. |
| 5 | `DOC-01` | El streaming token-a-token que el README vende como característica estrella no existe desde la migración a LangGraph. Es la divergencia más visible para un lector externo. |

> **Antes que los cinco:** `BUG-08` deja la aplicación sin arrancar de forma permanente cuando `/tmp` pierde el caché del re-ranker. Cuesta dos minutos y nada de lo anterior es verificable hasta resolverlo.

### Estado de remediación

Este documento es una foto del estado en la fecha de cabecera. Los inventarios, la traza y los anexos (§3, §9 y §11–§14) describen esa foto y no se reescriben con cada corrección: algunas de sus filas ya no son ciertas, como la de `PAPER.md` §5.4 sobre `BUG-05`. **El estado vigente de cada hallazgo es el de esta tabla y el de su línea `Estado:`.** Lo corregido desde entonces:

| Hallazgo | Estado | Fecha | Verificación |
|---|:---:|:---:|---|
| `BUG-08` | ✅ corregido | 2026-09-11 | Caché persistente + saneado automático; probado con caché sano, corrupto y override |
| `SEC-01` | ✅ corregido | 2026-09-11 | `JWT_SECRET_KEY` obligatoria por entorno, mínimo 32 caracteres; token con la clave antigua → 401 |
| `SEC-02` | ✅ corregido | 2026-09-11 | `tenant_id` tipado como `uuid.UUID` en el borde; inyección SQL en el token → 401; RLS verificado contra la BD real |
| `BUG-01` | ✅ corregido | 2026-09-11 | Objeto de stream separado del persistido; 4 de 8 filas contaminadas purgadas de `semantic_cache` |
| `BUG-03` | ✅ corregido | 2026-09-11 | Historial propagado hasta el supervisor; verificado en 5 fases con control negativo |
| `BUG-03` (derivado) | ✅ corregido | 2026-09-12 | El redactor también recibe el historial; formateo compartido en `history.py`. La respuesta a un seguimiento pasa de volcar 11 años del CV a una frase exacta |
| `DOC-01` | ✅ corregido | 2026-09-13 | Streaming token-a-token recuperado por el canal `custom` de LangGraph: 4 → 244 eventos SSE, primer texto 13,5 s → 9,6 s, medido contra servidor real |
| `BUG-09` | ✅ corregido | 2026-09-13 | Hallazgo nuevo: el stream no devolvía respuesta para saludos, fuera de alcance ni herramientas. Corregido con `DOC-01` |
| `SEC-04` | ✅ corregido | 2026-09-14 | Temporal con nombre aleatorio; el original solo como metadato. Control negativo contra uvicorn real: 1/9 → 9/9 propiedades; ingesta real 8/8 |
| `SEC-03` | ✅ corregido | 2026-09-14 | `ILIKE ANY($1::text[])` parametrizado. Con tokenizador permisivo, la versión vieja cae ante los tres payloads, incluida una lectura entre tenants; la nueva, ante ninguno. Mismos resultados en 16 consultas reales |
| `BUG-02` | ✅ corregido | 2026-09-14 | Lista blanca de intenciones, más confianza y `requires_more_info`, en ambos endpoints. Contra servidor real: 3/8 → 8/8. Antes, *"¿Cuánto vale ethereum?"* recibía el precio de bitcoin desde caché |
| `BUG-04` | ✅ corregido | 2026-09-14 | `00_create_app_user` → `01_init` completo; `apply_*` a `sql/migrations/`; healthcheck por TCP. Desde volumen vacío: `exit=3` → `healthy`. Catálogo idéntico al de desarrollo (77/77), RLS 7/7, app real 6/6 |
| `BUG-06` | ✅ corregido | 2026-09-14 | `top_k` propagados hasta el investigador, con valores por defecto únicos (15/10), límites de rango y sin caché cuando difieren. Contra servidor real: 3/8 → 8/8; fuera de rango 200 → 422 |
| `BUG-05` | ✅ corregido | 2026-09-14 | Opción (a): cada reintento amplía la ventana (15/10 → 30/15, con tope en los máximos de la API) y no se reintenta si ampliar no puede aportar nada. Contra servidor real: 3/7 → 7/7; reintentos idénticos 3 → 0 |
| `PERF-01` | ✅ corregido | 2026-09-15 | Pool único en `db.py` y `set_config` local a la transacción. Conexiones por consulta 8 → 0; 25 consultas concurrentes: 7 `TooManyConnectionsError` → 0; aislamiento verificado con pool de 2 |
| `PERF-02` | ✅ corregido | 2026-09-15 | Instancia única en `embeddings.py` con `to_pgvector`. Instancias 4 → 1; importación de la API 16,6 s → 5,6 s; *physical footprint* −102 MB (no 270–360 MB); resultados idénticos |
| `PERF-03` | ✅ corregido | 2026-09-15 | `chunk_text` y herramientas en `asyncio.to_thread`. Espera máxima de `/health`: ingesta 1182 → 21 ms, herramienta 204 → 14 ms; PDF de 20 páginas: parada del event loop 1060 → 16 ms, mismos fragmentos |
| `PERF-04` | ✅ corregido | 2026-09-15 | `max_tokens` 300 → 1024, `reasoning` ≤ 600 caracteres y `max_retries=3` explícito. Juez real, 15 evaluaciones por variante: perdidas 10/15 → 0/15 |
| `DOC-02` | ✅ corregido | 2026-09-15 | `ge`/`le` en las tres puntuaciones de `RAGEvaluation`: un 1,2 falla en Pydantic (reintentable) y no en el `CHECK` de SQL (pérdida silenciosa). Con `PERF-04` |
| `DOC-03` | ✅ corregido | 2026-09-16 | Arranque desde un clon limpio siguiendo solo README y `.env.example`. Antes: falla en el paso 2, y al completarlo la API conecta como `postgres` y **`empresa_x` recibe un dato de un documento de `bryan`**. Después: arranca a la primera como `app_user`, y el mismo dato no cruza de tenant (control positivo: `bryan` sí lo recibe) |
| `HYG-08` | ✅ corregido | 2026-09-16 | Volumen nombrado `pgdata`, con la base de desarrollo migrada sin pérdidas (copia en frío, `diff -r` sin diferencias). Control negativo con `compose down` + `up`: con el compose anterior, la fila marca desaparece y el volumen queda huérfano; con el nuevo, sobrevive |
| `BUG-10` | ✅ corregido | 2026-09-16 | Reproducido primero de extremo a extremo (le faltaba): el seguimiento de una conversación sobre Itaú/Kabeli recibía **literalmente** la respuesta de otra sobre MisterGas. Con el parche, cada una responde su propio referente y el caché no registra ningún acierto indebido |
| `SEC-06` | ✅ corregido | 2026-09-15 | Los tres puntos registran la traza y devuelven `Error interno (<id>)`. Contra servidor real: la ruta absoluta del temporal y el 401 de Anthropic pasan de llegar al cliente a existir solo en el log, correlacionados por el identificador |
| `SEC-05` | ✅ corregido | 2026-09-15 | Contexto de tenant firmado (HMAC-SHA256) verificado por una función `SECURITY DEFINER`. Contra la BD real, como `app_user`: la inyección del hallazgo pasa de leer **10 tripletas ajenas a 0**; sin firma o con firma falsa, 0 filas. Contra la API real: con la clave correcta, 4 fuentes y confianza 0,95; con una equivocada, 0 fuentes |
| Los otros 10 de la foto | ⬜ abiertos | — | — |
| `HYG-05`, `HYG-06` | ⬜ abiertos | 2026-09-14 | Hallazgos nuevos; ver §2 y el plan (§10) |
| `HYG-07` | ⬜ abierto | 2026-09-15 | Hallazgo nuevo, encontrado al corregir `SEC-05`; ver §2 y el plan (§10) |

**Pendientes de decisión sobre datos.** El código corregido ya no genera estas dos cosas, pero siguen en la base de desarrollo. No se tocaron sin que el usuario lo decida:

| # | Qué | Origen | Propuesta |
|---|---|---|---|
| D-01 | Las 22 filas de `documents` guardan en `metadata.source` la ruta temporal del servidor (`/var/folders/…/T/bbobadilla_resume.pdf`) | `SEC-04` | Dejar solo el nombre de archivo: `UPDATE documents SET metadata = jsonb_set(metadata, '{source}', to_jsonb(regexp_replace(metadata->>'source', '^.*/', ''))) WHERE metadata->>'source' LIKE '/%';` como `postgres` |
| D-02 | Una fila de `semantic_cache` (`7f55b002…`, `requires_more_info=true`, confianza 0,75) que la política de `BUG-02` no guardaría y que se sigue sirviendo | `BUG-02` | Borrarla |

**Correcciones a la foto.** Al verificar contra el sistema real, algunas afirmaciones de este documento resultaron incompletas o incorrectas. El detalle está en la línea de estado de cada hallazgo:

- **`SEC-03`**: se daba por hecho que RLS contenía una inyección en esa consulta. No la contiene: `app_user` puede reescribir su tenant desde la propia sentencia (catalogado como `SEC-05`).
- **`SEC-04`**: el path traversal no solo sobrescribe el destino; el `finally` lo borra. Además, el parche propuesto, aplicado solo, habría perdido el nombre original de cada documento.
- **`BUG-02`**: el caché no solo servía datos viejos, sino datos de otra consulta (el precio de bitcoin a quien preguntaba por ethereum). `out_of_scope` no es inocuo. Desde la corrección de `BUG-09`, `/chat/stream/` también cacheaba herramientas.
- **`BUG-04`**: `FORCE ROW LEVEL SECURITY` no protege el DSN de `postgres` de `.env.example`, porque un superusuario elude RLS con o sin `FORCE`.
- **`PERF-04`**: el evaluador no fallaba siempre, como dice el commit `d198be1` (`BUG-02`), pero tampoco de vez en cuando: con un contexto realista de 10 documentos perdía **10 de cada 15** evaluaciones por `max_tokens`.
- **`PERF-01`**: la fuga entre tenants que se temía al reutilizar conexiones no llegaría a producirse con asyncpg 0.31, cuyo `RESET ALL` al devolver una conexión borra el tenant de sesión (medido). Con un reset vacío la fuga sí aparece. Tampoco era cierto que los nueve accesos usaran `app_user`: `ingestion.py` usaba por defecto el superusuario.
- **`DOC-03`**: el riesgo de seguridad era real de extremo a extremo, no solo en teoría: con la plantilla, un tenant recibió por la API un dato de un documento de otro. Además, `SEC-05` había añadido una rotura que la foto no podía contener: el README levantaba la base antes de crear `.env`, y Compose ya no arranca sin `TENANT_SIGNING_KEY`.
- **`BUG-10`**: el hallazgo se catalogó como verificado solo por lectura de código. Reproducido el 2026-09-16, resultó ser exactamente lo descrito y algo más: la respuesta servida desde el caché arranca con *"Según el historial anterior"*, atribuyéndole al usuario una conversación ajena.
- **`SEC-05`**: el parche propuesto (opción 1) no bastaba tal como estaba descrito. Guardar la clave en una tabla de `public` "sin `GRANT` a `app_user`" no la protege: `sql/00_create_app_user.sql` deja un `ALTER DEFAULT PRIVILEGES IN SCHEMA public ... GRANT ALL ON TABLES TO app_user`, así que la tabla nace con un `GRANT` explícito al rol y `REVOKE ... FROM PUBLIC` no lo deshace. La primera versión del parche pasó todas las pruebas de aislamiento y aun así `app_user` podía leer la clave y firmar cualquier tenant; se descubrió porque el control negativo lo comprobaba explícitamente. La clave vive ahora en un esquema propio (`tenant_security`). El `ALTER DEFAULT PRIVILEGES` queda catalogado aparte como `HYG-07`.
- **`PERF-02`**: las tres copias sobrantes del modelo costaban ~102 MB de *physical footprint* medido, no los 270–360 MB estimados. La estimación de que consolidarlas acortaba el arranque sí se confirma: la importación de la API pasa de 16,6 s a 5,6 s.

---

## 2. Índice de Hallazgos

| ID | Sev. | Título | Ubicación principal | Bloque |
|---|:---:|---|---|:---:|
| `SEC-01` | 🔴 | `SECRET_KEY` del JWT hardcodeado y versionado | `src/api/auth.py:8` | 1 |
| `SEC-02` | 🔴 | `tenant_id` interpolado sin validar en `SET` | 9 puntos en `src/services/` | 1 |
| `SEC-03` | 🟠 | `WHERE` construido por concatenación en GraphRAG | `src/services/graphrag.py:80` | 1 |
| `SEC-04` | 🟡 | Path traversal vía `filename` en la ingesta | `src/api/routers/ingest.py:23` | 1 |
| `BUG-01` | 🟠 | Caché envenenado con el prefijo de progreso | `src/api/routers/chat.py:119` | 2 |
| `BUG-02` | 🟠 | El caché intercepta las ejecuciones de herramientas | `src/api/routers/chat.py:27,77` | 2 |
| `BUG-03` | 🟠 | El historial de conversación se descarta | `src/services/agent_graph/nodes.py:18` | 2 |
| `BUG-04` | 🟠 | Bootstrap de Docker roto por orden de scripts SQL | `docker-compose.yml:9` | 2 |
| `BUG-05` | 🟡 | El ciclo de auto-corrección no corrige nada | `src/services/agent_graph/graph.py:11` | 2 |
| `BUG-06` | 🟡 | `top_k_retrieve` / `top_k_rerank` son decorativos | `src/models/requests.py:7` | 2 |
| `BUG-07` | 🟡 | La única suite de tests no puede ejecutarse | `tests/test_rag.py:28` | 5 |
| `BUG-08` | 🟠 | Caché del re-ranker en `/tmp`: la app deja de arrancar al perderse | `src/services/reranker.py:10` | 0 |
| `BUG-09` | 🟠 | `/chat/stream/` no responde a saludos, fuera de alcance ni herramientas | `src/api/routers/chat.py:102` | 2 |
| `PERF-01` | 🟠 | Sin connection pool: ~11 conexiones por consulta | 9 `asyncpg.connect()` | 3 |
| `PERF-02` | 🟠 | Cuatro copias del modelo de embeddings en RAM | 4 módulos de `src/services/` | 3 |
| `PERF-03` | 🟡 | `model.encode` bloquea el event loop en la ingesta | `src/services/ingestion.py:72` | 3 |
| `PERF-04` | 🟡 | `max_tokens=300` trunca al evaluador | `src/services/evaluator.py:60` | 3 |
| `DOC-01` | 🟠 | El streaming token-a-token ya no existe | `src/services/extractor.py:56` | 4 |
| `DOC-02` | 🟠 | El paper afirma validaciones Pydantic inexistentes | `src/services/evaluator.py:14` | 4 |
| `DOC-03` | 🟠 | `.env.example` no permite arrancar el proyecto | `.env.example` | 4 |
| `DOC-04` | 🟡 | `NetworkX` documentado pero nunca usado | `README.md` | 4 |
| `DOC-05` | 🟡 | `ARCHITECTURE.md` congelado en la Fase 1 | `ARCHITECTURE.md` | 4 |
| `DOC-06` | 🟡 | Chunking: 400 tokens en código vs 500 en el paper | `src/services/ingestion.py:48` | 4 |
| `DOC-07` | 🟡 | Modelo LLM mal citado en toda la documentación | 7 llamadas + `README.md` | 4 |
| `DOC-08` | ⚪ | Python 3.12 (badge) vs 3.14 (`requires-python`) | `pyproject.toml:3` | 4 |
| `HYG-01` | 🟡 | Dependencias directas no declaradas | `pyproject.toml` | 5 |
| `HYG-02` | 🟡 | Código muerto versionado en la raíz | raíz del repo | 5 |
| `HYG-03` | ⚪ | `.gitignore` incompleto | `.gitignore` | 5 |
| `HYG-04` | ⚪ | `datetime.utcnow()` deprecado | `src/api/auth.py:41,43` | 5 |
| `SEC-05` | 🟠 | `app_user` puede reescribir su propio contexto de tenant | políticas RLS de `sql/01_init.sql` | 3 |
| `SEC-06` | 🟡 | Las respuestas de error devuelven el texto de la excepción | `src/api/routers/ingest.py:39` | 1 |
| `BUG-10` | 🟠 | El caché semántico ignora el historial | `src/services/cache.py:17` | 2 |
| `HYG-05` | 🟡 | Tres servicios crean su cliente de Anthropic antes de cargar `.env` | `src/services/router.py:10` | 5 |
| `HYG-06` | ⚪ | La base de datos no se reinicia con Docker | `docker-compose.yml` | 5 |
| `HYG-07` | 🟡 | `ALTER DEFAULT PRIVILEGES` regala a `app_user` cualquier tabla futura de `public` | `sql/00_create_app_user.sql:5` | 5 |
| `HYG-08` | 🟠 | Los datos de la base viven en un volumen anónimo | `docker-compose.yml` | 5 |

Las siete últimas filas son posteriores a la foto (cinco del 2026-09-14, `HYG-07` del 2026-09-15 y `HYG-08` del 2026-09-16) y no entran en el recuento de §1.

---

## 3. Inventario Verificado del Sistema

Estado real de cada archivo, contrastado contra el inventario de `PAPER_PLAN.md` §1.

### 3.1. Capa de API

| Archivo | Líneas | Estado | Observaciones |
|---|:---:|:---:|---|
| `src/api/main.py` | 28 | ✅ | CORS con `allow_origins=["*"]` + `allow_credentials=True`; sin `lifespan` (ver `PERF-01`) |
| `src/api/auth.py` | 80 | ⚠️ | `SEC-01`, `SEC-02`, `HYG-04`. Usuarios mock en fuente |
| `src/api/routers/chat.py` | 132 | ⚠️ | `BUG-01`, `BUG-02`. Dos endpoints: `/chat/` (síncrono) y `/chat/stream/` (SSE) |
| `src/api/routers/ingest.py` | 39 | ⚠️ | `SEC-04`. Validación de extensión correcta |
| `src/api/__init__.py` | 0 | ✅ | vacío |
| `src/api/routers/__init__.py` | 0 | ✅ | vacío |

### 3.2. Orquestación LangGraph

| Archivo | Líneas | Estado | Observaciones |
|---|:---:|:---:|---|
| `src/services/agent_graph/state.py` | 28 | ⚠️ | `AgentState` sin campo `history` (`BUG-03`); `messages` declarado con reductor `operator.add` pero nunca poblado |
| `src/services/agent_graph/graph.py` | 51 | ⚠️ | `BUG-05`. Topología correcta: 3 nodos, 2 aristas condicionales |
| `src/services/agent_graph/nodes.py` | 116 | ⚠️ | `BUG-03`, `BUG-06`. Los 3 nodos bien separados |
| `src/services/agent_graph/__init__.py` | 0 | ✅ | vacío |

**Topología verificada** (`graph.py:20-51`):

```
                    ┌──────────────┐
     entry ────────▶│  supervisor  │
                    └──────┬───────┘
                           │ route_supervisor
              ┌────────────┴────────────┐
              │ final_answer presente?  │
         sí ──┴── END          no ──────┴──▶┌────────────┐
                                            │ researcher │◀──┐
                                            └─────┬──────┘   │
                                                  │ (arista  │
                                                  │  directa)│
                                            ┌─────▼──────┐   │
                                            │ generator  │   │
                                            └─────┬──────┘   │
                                                  │ route_reviewer
                                    needs_more_info ∧ iter<2 ┘
                                                  │
                                                 END
```

### 3.3. Servicios

| Archivo | Líneas | LLM | Postgres | Estado | Observaciones |
|---|:---:|:---:|:---:|:---:|---|
| `src/services/router.py` | 81 | ✅ | — | ✅ | Prompt bien construido; el parámetro `history` nunca recibe datos (corregido, `BUG-03`) |
| `src/services/history.py` | 33 | — | — | ✅ | Añadido al corregir `BUG-03`: formatea la ventana de historial para router y redactor |
| `src/services/retriever.py` | 75 | — | ✅ | ⚠️ | `SEC-02`, `PERF-01`, `PERF-02`. RRF correcto |
| `src/services/reranker.py` | 46 | — | — | ⚠️ | `BUG-08`. Instancia única del `Ranker`; usa `asyncio.to_thread` correctamente |
| `src/services/extractor.py` | 90 | ✅ | — | ⚠️ | `DOC-01`: `generate_answer_stream` (l. 56-90) es código muerto (corregido: hoy es el camino normal) |
| `src/services/graphrag.py` | 99 | ✅ | ✅ | ⚠️ | `SEC-02`, `SEC-03`, `PERF-01` |
| `src/services/ingestion.py` | 267 | ✅ | ✅ | ⚠️ | `DOC-06`, `PERF-02`, `PERF-03`. Multimodal (MD/TXT/PDF/imagen) correcto |
| `src/services/cache.py` | 62 | — | ✅ | ⚠️ | `SEC-02`, `PERF-01`, `PERF-02` |
| `src/services/memory.py` | 97 | ✅ | ✅ | ⚠️ | `SEC-02`, `PERF-01`, `PERF-02` |
| `src/services/evaluator.py` | 87 | ✅ | ✅ | ⚠️ | `DOC-02`, `PERF-04`. Único módulo sin `load_dotenv()` |
| `src/services/tools.py` | 48 | — | — | ⚠️ | `requests` síncrono dentro de ruta `async`; timeout 5 s correcto |

**Nota sobre `evaluator.py`.** Es el único servicio que no llama a `load_dotenv()` (comparar con `retriever.py:5-6`, `cache.py:9`, `memory.py:10`, `graphrag.py:10`, `ingestion.py:17`). Funciona hoy solo porque se importa después de módulos que sí la llaman y `os.environ` ya está poblado. Es una dependencia de orden de importación no declarada: si `evaluator.py` se importara primero, `DB_DSN` caería al default y `ANTHROPIC_API_KEY` sería `None`.

**Nota sobre `tools.py`.** Las tres herramientas usan `requests` (síncrono) y se invocan desde `supervisor_node`, que es `async` (`nodes.py:40`: `tool_result = tool_func(**intent.tool_args)`). Cada llamada a CoinGecko o GitHub bloquea el event loop hasta 5 segundos. No se cataloga como hallazgo independiente porque comparte causa y corrección con `PERF-03`.

### 3.4. Modelos y contratos

| Archivo | Líneas | Estado | Observaciones |
|---|:---:|:---:|---|
| `src/models/structured.py` | 12 | ✅ | `confidence_score` **sí** tiene `ge=0.0, le=1.0` (contrastar con `DOC-02`) |
| `src/models/search.py` | 11 | ✅ | `RerankedResult` hereda correctamente de `SearchResult` |
| `src/models/requests.py` | 11 | ⚠️ | `BUG-06`: `top_k_*` ignorados. `IngestRequest` (l. 10-11) no se usa en ningún endpoint |

### 3.5. Esquema de datos

| Archivo | Tablas | `ENABLE RLS` | `FORCE RLS` | `GRANT` | Estado |
|---|---|:---:|:---:|:---:|:---:|
| `sql/01_init.sql` | `documents`, `semantic_cache`, `user_memory`, `rag_evaluations` | ✅ 4/4 | ❌ 0/4 | ❌ | ⚠️ |
| `sql/apply_rls.sql` | `documents` (migración) | ✅ | ❌ | ❌ | ✅ |
| `sql/apply_cache.sql` | `semantic_cache` | ✅ | ✅ | ⚠️ falla | ⚠️ |
| `sql/apply_memory.sql` | `user_memory` | ✅ | ✅ | ⚠️ falla | ⚠️ |
| `sql/apply_evaluator.sql` | `rag_evaluations` | ✅ | ✅ | ⚠️ falla | ⚠️ |
| `sql/apply_graphrag.sql` | `knowledge_graph` | ✅ | ✅ | ⚠️ falla | ⚠️ |
| `sql/create_app_user.sql` | — (crea rol) | — | ✅ solo `documents` | ✅ | ⚠️ |

Los `GRANT` marcados como "falla" son los de `BUG-04`: se ejecutan antes de que exista el rol `app_user`.

**Hueco de cobertura.** `sql/01_init.sql` —el script que `PAPER_PLAN.md` §1 describe como *"script unificado"*— **no crea `knowledge_graph`** y **no aplica `FORCE ROW LEVEL SECURITY` a ninguna tabla**. Sin `FORCE`, el propietario de la tabla elude sus propias políticas RLS. Si alguien conecta con el DSN de `.env.example` (usuario `postgres`, que es el propietario), el aislamiento multi-tenant no se aplica en absoluto sobre las cuatro tablas de `01_init.sql`. Ver `DOC-03`.

### 3.6. Código muerto confirmado

| Archivo | Motivo | Referencia |
|---|---|---|
| `src/pipeline.py` (44 l.) | `retrieve_documents(query, top_k=5)` sin `tenant_id` → `TypeError` | `HYG-02` |
| ~~`src/services/extractor.py:56-90`~~ | ~~`generate_answer_stream` nunca invocada~~ — resucitada al corregir `DOC-01` | `DOC-01` |
| `tests/test_rag.py` (rota) | mismo `TypeError` en l. 28 | `BUG-07` |
| `src/models/requests.py:10-11` | `IngestRequest` nunca usada (el endpoint usa `UploadFile`) | `HYG-02` |
| `src/services/ingestion.py:48` | parámetro `overlap` declarado y nunca leído | `DOC-06` |
| `src/services/agent_graph/state.py:9` | `messages` declarado, siempre `[]` | `BUG-03` |
| `test_chunk.py`, `test_db.py`, `test_sim.py`, `test_sse.py` | scripts de validación local en la raíz | `HYG-02` |
| `scratch_db.py`, `scratch_stream.py` | experimentos en la raíz | `HYG-02` |
| `uvicorn.log` (153 B) | log versionado | `HYG-03` |

Verificación:

```bash
grep -rn "generate_answer_stream\|IngestRequest\|networkx" src/ tests/
# única coincidencia: la definición en extractor.py:56 y requests.py:10
```

---

## 4. Seguridad

### `SEC-01` 🔴 `SECRET_KEY` del JWT hardcodeado y versionado

**Ubicación.** `src/api/auth.py:8-10`

```python
SECRET_KEY = "super_secret_ai_sandbox_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
```

**Análisis.** HS256 es un algoritmo **simétrico**: la misma clave firma y verifica. `create_access_token` (l. 38-46) firma con ella y `get_current_user` (l. 72) verifica con ella. Quien conoce la clave puede emitir tokens indistinguibles de los legítimos.

La clave está en un repositorio público de portafolio. No es un secreto.

**Cadena de explotación completa.**

1. Leer `auth.py:8` → obtener `SECRET_KEY`.
2. Firmar un token con `tenant_id` arbitrario:
   ```python
   import jwt, datetime
   token = jwt.encode(
       {"sub": "attacker",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
       "super_secret_ai_sandbox_key", algorithm="HS256")
   ```
3. `get_current_user` (l. 72-80) lo valida sin objeciones: comprueba firma, `sub` y `tenant_id` no nulos. Nada más.
4. El `tenant_id` se propaga a `SET app.current_tenant` en las nueve rutas de datos. **RLS concede acceso legítimamente**, porque desde su punto de vista la petición está autorizada.

**Qué queda expuesto.** Las cinco tablas del tenant víctima: `documents` (contenido íntegro de los archivos ingeridos), `user_memory` (hechos personales extraídos silenciosamente en background), `semantic_cache` (histórico de preguntas y respuestas), `rag_evaluations` (consultas evaluadas) y `knowledge_graph` (grafo de entidades).

**Impacto documental.** Anula el argumento central de tres documentos: `README.md` §3 (*"Total aislamiento de datos de clientes"*), `PAPER.md` §4.4 y `GRAPHRAG_ARCHITECTURE.md` §1. Las políticas RLS son correctas y funcionan; el problema es que la **entrada** al sistema es falsificable.

**Agravante.** Las credenciales mock están en el mismo fuente (`auth.py:23-34`): `bryan` / `password123` y `empresa_x` / `password123`. Ni siquiera hace falta forjar un token para entrar como cualquiera de los dos tenants.

**Reproducción.**

```bash
grep -n "SECRET_KEY\|password" src/api/auth.py
# 8:  SECRET_KEY = "super_secret_ai_sandbox_key"
# 26:     "password": "password123",
# 32:     "password": "password123",
```

**Parche.**

```diff
--- a/src/api/auth.py
+++ b/src/api/auth.py
@@
+import os
+
-SECRET_KEY = "super_secret_ai_sandbox_key"
+# Sin valor por defecto: el proceso debe fallar al arrancar si no está configurada.
+SECRET_KEY = os.environ["JWT_SECRET_KEY"]
 ALGORITHM = "HS256"
```

Añadir a `.env.example` (ver `DOC-03`):

```
# Generar con: openssl rand -hex 32
JWT_SECRET_KEY=cambia_esto_por_una_clave_aleatoria_de_32_bytes
```

Los usuarios mock son aceptables en un sandbox declarado, pero conviene un comentario explícito de que `FAKE_USERS_DB` no es un sistema de autenticación y que las contraseñas no están hasheadas.

**Estado: ✅ corregido (2026-09-11).** `SECRET_KEY` pasa a leerse de `JWT_SECRET_KEY` sin valor por defecto: si falta, o mide menos de 32 caracteres, el proceso no arranca. Un token firmado con la clave antigua devuelve 401. Añadido también el comentario sobre `FAKE_USERS_DB`.

---

### `SEC-02` 🔴 `tenant_id` interpolado sin validar en `SET app.current_tenant`

**Ubicación.** Nueve puntos, sintaxis idéntica:

| Archivo:línea | Función |
|---|---|
| `src/services/retriever.py:32` | `retrieve_documents` |
| `src/services/cache.py:23` | `check_semantic_cache` |
| `src/services/cache.py:51` | `save_semantic_cache` |
| `src/services/memory.py:50` | `extract_and_save_facts` |
| `src/services/memory.py:72` | `retrieve_user_facts` |
| `src/services/graphrag.py:53` | `insert_knowledge_graph` |
| `src/services/graphrag.py:67` | `retrieve_subgraph` |
| `src/services/evaluator.py:68` | `evaluate_rag_response` |
| `src/services/ingestion.py:186` | `insert_documents` |

```python
await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
```

**Sobre la interpolación en sí.** `SET` no admite parámetros vinculados en el protocolo extendido de PostgreSQL, así que construir la sentencia como string es técnicamente inevitable con asyncpg. **Eso no es el defecto.**

**El defecto** es que `tenant_id` viaja sin validación desde el payload del JWT hasta la sentencia SQL:

```
JWT payload (auth.py:74)  →  User.tenant_id: str (auth.py:20)
                          →  current_user.tenant_id (chat.py:27)
                          →  AgentState["tenant_id"] (chat.py:37)
                          →  f"SET app.current_tenant = '{tenant_id}'"
```

`User.tenant_id` está tipado como `str` (`auth.py:20`), que acepta cualquier cadena. En ningún punto de esa cadena se comprueba que sea un UUID.

**Cadena de explotación.** Encadenado con `SEC-01`, un token forjado con

```python
"tenant_id": "x'; DROP TABLE documents CASCADE; --"
```

produce la sentencia:

```sql
SET app.current_tenant = 'x'; DROP TABLE documents CASCADE; --'
```

`conn.execute()` de asyncpg usa el protocolo simple cuando no hay parámetros, que **permite múltiples sentencias separadas por `;`**. Se ejecuta con los privilegios de `app_user`, al que `sql/create_app_user.sql:2-5` concede `ALL PRIVILEGES` sobre la base entera. El `ON DELETE CASCADE` de `knowledge_graph.source_chunk_id` (`apply_graphrag.sql:7`) propaga la destrucción al grafo.

**Reproducción.**

```bash
grep -rn "SET app.current_tenant" src/ | wc -l   # 9
grep -n "tenant_id: str" src/api/auth.py          # 20: tenant_id: str
```

**Parche.** Una sola línea en el borde cierra el vector completo para las nueve rutas:

```diff
--- a/src/api/auth.py
+++ b/src/api/auth.py
@@
+import uuid
 from pydantic import BaseModel
@@
 class User(BaseModel):
     username: str
-    tenant_id: str
+    tenant_id: uuid.UUID   # Pydantic rechaza cualquier cosa que no sea un UUID válido
```

Con el tipado a `uuid.UUID`, Pydantic valida en la construcción de `User` (l. 80) y `get_current_user` lanza `ValidationError` antes de que el valor toque la capa de datos. Los servicios reciben entonces un objeto `UUID`, cuya representación en f-string es siempre la forma canónica de 36 caracteres hexadecimales y guiones — sin comillas posibles.

Si se prefiere no cambiar el tipo público, la alternativa explícita:

```python
try:
    uuid.UUID(tenant_id)
except (ValueError, TypeError, AttributeError):
    raise credentials_exception
```

**Defensa en profundidad recomendada.** Aunque el borde quede validado, conviene usar la función de quoting del servidor en lugar de la interpolación directa:

```python
await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant_id))
```

`set_config()` es una función SQL normal y acepta parámetros vinculados, eliminando la interpolación por completo en los nueve puntos. Es la corrección definitiva.

**Estado: ✅ corregido (2026-09-11).** `User.tenant_id` pasa a tiparse como `uuid.UUID`, de modo que Pydantic rechaza en el borde cualquier valor capaz de transportar SQL: un `tenant_id` malicioso en el token devuelve 401 en lugar de llegar al `SET`. La firma de las nueve funciones aguas abajo se actualizó a `uuid.UUID`, y `ingest.py` valida el argumento `--tenant` con `type=uuid.UUID`. Verificado el aislamiento RLS contra la base real. La defensa en profundidad con `set_config()` queda pendiente.

**Actualización (2026-09-15, con `PERF-01`).** La defensa en profundidad queda aplicada. Ninguna consulta interpola ya el tenant: `tenant_connection()` (`src/services/db.py`) lo fija como parámetro con `set_config('app.current_tenant', $1, true)`, local a una transacción, y es el único punto del código que lo hace. Lo que sigue abierto es que una sentencia inyectada pueda reescribirlo (`SEC-05`), algo que un parámetro no evita.

---

### `SEC-03` 🟠 `WHERE` construido por concatenación en GraphRAG

**Ubicación.** `src/services/graphrag.py:69-89`

```python
import re
words = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 3]
if not words:
    return ""

conditions = []
for word in words:
    conditions.append(f"source_node ILIKE '%{word}%' OR target_node ILIKE '%{word}%'")

sql_query = f"""
SELECT source_node, relation, target_node
FROM knowledge_graph
WHERE {' OR '.join(conditions)}
LIMIT 10
"""

rows = await conn.fetch(sql_query)
```

**Análisis.** Se interpolan fragmentos derivados de la **consulta en lenguaje natural del usuario** —dato completamente no confiable— directamente en la cláusula `WHERE`.

**Estado actual: no explotable.** `re.findall(r'\w+', query)` en Python 3 con strings Unicode captura `[a-zA-Z0-9_]` más caracteres alfanuméricos Unicode. La comilla simple (`'`) no pertenece a `\w`, de modo que nunca sobrevive al filtro. La inyección está bloqueada.

**Por qué sigue siendo un hallazgo.** La seguridad de esta consulta no depende del mecanismo de acceso a datos sino de un regex situado ocho líneas más arriba, sin ningún comentario que explique esa responsabilidad. Escenarios plausibles que la rompen:

- Permitir guiones para capturar entidades como `multi-tenant` → `r'[\w-]+'` sigue siendo seguro, pero es un cambio a ciegas.
- Cambiar a búsqueda por frases en lugar de palabras sueltas (mejora natural del GraphRAG) → introduce espacios y probablemente puntuación.
- Relajar `len(w) > 3` o el patrón para soportar otro idioma o alfabeto.

Cualquiera de esos cambios reintroduce la inyección sin que nada en el código lo señale.

**Coste secundario.** La construcción también es ineficiente: con 8 palabras clave genera 16 predicados `ILIKE` con comodín inicial (`'%word%'`), que **no pueden usar los índices B-Tree** `kg_source_idx` y `kg_target_idx` de `apply_graphrag.sql:10-11`. Cada consulta al grafo es un *sequential scan* completo de `knowledge_graph`.

**Reproducción.**

```bash
sed -n '69,89p' src/services/graphrag.py
```

**Parche.** Array parametrizado con `ILIKE ANY`:

```diff
-        conditions = []
-        for word in words:
-            conditions.append(f"source_node ILIKE '%{word}%' OR target_node ILIKE '%{word}%'")
-
-        sql_query = f"""
-        SELECT source_node, relation, target_node
-        FROM knowledge_graph
-        WHERE {' OR '.join(conditions)}
-        LIMIT 10
-        """
-
-        rows = await conn.fetch(sql_query)
+        patterns = [f"%{w}%" for w in words]
+        sql_query = """
+        SELECT source_node, relation, target_node
+        FROM knowledge_graph
+        WHERE source_node ILIKE ANY($1::text[])
+           OR target_node ILIKE ANY($1::text[])
+        LIMIT 10
+        """
+        rows = await conn.fetch(sql_query, patterns)
```

Más corto, seguro con independencia del regex, y con un plan de ejecución estable (una sola preparación de sentencia en lugar de una distinta por cada combinación de palabras).

Para recuperar el uso de índices, la mejora complementaria es un índice trigram:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX kg_source_trgm_idx ON knowledge_graph USING GIN (source_node gin_trgm_ops);
CREATE INDEX kg_target_trgm_idx ON knowledge_graph USING GIN (target_node gin_trgm_ops);
```

**Estado: ✅ corregido (2026-09-14).** Aplicado el parche de arriba. Las palabras de la consulta viajan como parámetro y la seguridad deja de depender del regex. `%` y `_` dentro de una palabra siguen actuando como comodines de `ILIKE`, igual que antes. Escaparlos no aporta seguridad, porque un parámetro no puede alterar el SQL, y cambiaría resultados sobre datos reales: 13 tripletas de la base tienen nodos con `_` (`api_gateway`, `buenas_prácticas_de_desarrollo`…). El índice trigram no se aplica aquí: es rendimiento, no seguridad, y requiere tocar los scripts SQL, lo que conviene hacer junto con `BUG-04`.

Verificado ejecutando la versión anterior y la nueva contra Postgres real, conectadas como `app_user` (sin `SUPERUSER` ni `BYPASSRLS`, con `FORCE ROW LEVEL SECURITY`).

*Control negativo.* Se sustituyó el tokenizador por uno permisivo, el escenario que este hallazgo anticipa:

| Payload | Antes | Después |
|---|---|---|
| Tautología (`…%' or true or source_node ilike '%…`) | 10 filas sin coincidir ninguna palabra | 0 filas |
| Apóstrofo legítimo (`o'brien`) | `PostgresSyntaxError`: el investigador cae | 0 filas |
| Lectura entre tenants, como un tenant sin tripletas | **10 tripletas del otro tenant** | 0 filas |

**La tercera fila corrige la valoración de este hallazgo.** Se daba por supuesto que una inyección aquí quedaba contenida por RLS. No es así. El payload añade un `UNION` cuyo `FROM` ejecuta `set_config('app.current_tenant', '<otro tenant>', false)` antes de recorrer `knowledge_graph`, y la política RLS evalúa `current_setting` fila a fila, así que lee ya el tenant reescrito. `app_user` puede cambiar la variable de la que depende su propio aislamiento. Por eso **cualquier** inyección SQL en el sistema anula el aislamiento multi-tenant, no solo esta. Catalogado como `SEC-05`.

*Equivalencia.* Con el tokenizador real, 16 consultas sobre los datos del tenant con grafo: mismo conjunto completo de coincidencias sin `LIMIT` (0 a 21 filas) y misma salida de `retrieve_subgraph` en las 16. Otras tres comprobaciones: el tenant sin tripletas no ve nada con ninguna consulta, `researcher_node` real antepone el subgrafo (10 tripletas) al contexto, y la base queda sin cambios, porque la prueba solo lee.

---

### `SEC-04` 🟡 Path traversal vía `filename` en la ingesta

**Ubicación.** `src/api/routers/ingest.py:15-27`

```python
ext = os.path.splitext(file.filename)[1].lower()
if ext not in ALLOWED_EXTENSIONS:
    raise HTTPException(status_code=400, detail=f"Extensión no permitida...")

temp_dir = tempfile.gettempdir()
temp_file_path = os.path.join(temp_dir, file.filename)

with open(temp_file_path, "wb") as buffer:
    shutil.copyfileobj(file.file, buffer)
```

**Análisis.** `file.filename` procede de la cabecera `Content-Disposition` de la petición multipart y es enteramente controlado por el cliente. Se usa sin sanear en `os.path.join`, que tiene la propiedad de **resolver componentes relativos**:

```python
os.path.join("/tmp", "../../home/user/.config/nvim/init.txt")
# → '/tmp/../../home/user/.config/nvim/init.txt'  → escribe fuera de /tmp
```

**Mitigación parcial existente.** El comentario de la línea 10 (*"Archivos permitidos para evitar vulnerabilidades"*) muestra que la intención defensiva está presente, y la validación de extensión (l. 18) limita los destinos a `.md`, `.txt`, `.pdf`, `.png`, `.jpg`, `.jpeg`. Eso **reduce** el impacto pero no lo elimina: sigue siendo posible sobrescribir cualquier archivo con esas extensiones al que el proceso tenga acceso de escritura. Requiere autenticación previa — que `SEC-01` vuelve trivial.

**Segundo defecto en el mismo bloque: colisión de nombres.** Al derivar el path del nombre original, dos usuarios (de tenants distintos) que suban `cv.pdf` simultáneamente escriben sobre el mismo `/tmp/cv.pdf`. Escenario concreto:

1. Tenant A sube `cv.pdf` → se escribe en `/tmp/cv.pdf`, empieza `ingest_file`.
2. Tenant B sube su `cv.pdf` → **sobrescribe** `/tmp/cv.pdf`.
3. `ingest_file` de A, que aún está leyendo el archivo (`ingestion.py:218` o `process_pdf`), ingiere el documento de B **bajo el `tenant_id` de A**.
4. El `finally` de la línea 37-38 borra el archivo, y la segunda ingesta puede fallar por archivo inexistente.

Es una fuga de datos entre tenants por condición de carrera, independiente de `SEC-01`.

**Reproducción.**

```bash
sed -n '20,27p' src/api/routers/ingest.py
```

**Parche.** `NamedTemporaryFile` resuelve ambos problemas a la vez:

```diff
-    temp_dir = tempfile.gettempdir()
-    temp_file_path = os.path.join(temp_dir, file.filename)
-
     try:
-        with open(temp_file_path, "wb") as buffer:
+        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as buffer:
+            temp_file_path = buffer.name
             shutil.copyfileobj(file.file, buffer)
```

`NamedTemporaryFile` genera un nombre aleatorio dentro del directorio temporal (sin traversal posible) y único (sin colisión). Requiere mover la declaración de `temp_file_path` e inicializarla a `None` antes del `try` para que el `finally` siga siendo válido.

Alternativa mínima si se quiere conservar el nombre original con fines de trazabilidad —el nombre se persiste como `metadata["source"]` en `ingestion.py:195`:

```python
safe_name = os.path.basename(file.filename)
temp_file_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{safe_name}")
```

**Estado: ✅ corregido (2026-09-14).** El archivo va a disco con `NamedTemporaryFile` y `file.filename` ya no toca ninguna ruta: se reduce a su `basename` y viaja como metadato por un parámetro nuevo, `ingest_file(..., source=...)`. El parche de arriba, aplicado solo, habría cambiado `metadata["source"]` por el nombre aleatorio del temporal, porque `ingest_file` lo derivaba de la ruta de disco. Por la misma razón, las 22 filas de `documents` de la base auditada guardan como fuente la ruta temporal completa del servidor (`/var/folders/…/T/bbobadilla_resume.pdf`).

**El impacto era mayor que el descrito.** El `finally` borra el archivo al terminar, así que el traversal no solo sobrescribe el destino: lo **elimina**.

Verificado contra uvicorn real con el multipart construido a mano, para que ningún cliente sanee el nombre (starlette 1.6 no lo hace). `ingest_file` se sustituyó por un doble que registra la ruta y el contenido recibidos:

| Propiedad | Antes | Después |
|---|:---:|:---:|
| La ruta de disco queda dentro del directorio temporal | ❌ | ✅ |
| Un archivo víctima alcanzado con `../` sobrevive | ❌ borrado | ✅ |
| El nombre visible es el `basename`, sin directorios | ❌ | ✅ |
| Dos tenants subiendo `cv.txt` a la vez ingieren cada uno el suyo | ❌ el tenant A ingirió el de B | ✅ |
| Ambas subidas terminan en 200 | ❌ B → 500 (el `finally` de A borró su archivo) | ✅ |
| Rutas temporales distintas | ❌ | ✅ |
| Temporales borrados tras la petición | ✅ | ✅ |

En la carrera, el doble espera 0,5 s antes de leer para que la ventana no dependa del azar del scheduler. La carrera existe igual sin esa espera.

Ingesta real (Claude y Postgres, sin dobles) de un `.txt` y un `.png` subidos como `../../intruso/<nombre>`: 8/8. `metadata.source` y la etiqueta `[Imagen …]` llevan el nombre original, las filas quedan bajo el tenant del token y GraphRAG extrae sus tripletas. La base se devolvió a su estado inicial.

Queda fuera de este hallazgo: el `except` del endpoint devuelve `detail=str(e)`, y en la prueba de carrera ese 500 entregó al cliente la ruta interna del servidor. Catalogado como `SEC-06`.

---

### `SEC-05` 🟠 `app_user` puede reescribir su propio contexto de tenant

> Posterior a la foto: encontrado el 2026-09-14 al verificar `SEC-03`.

**Ubicación.** Las cinco políticas RLS de `sql/01_init.sql`, que filtran por `current_setting('app.current_tenant')`, y el rol `app_user` de `sql/00_create_app_user.sql`, con el que conecta la aplicación.

**Análisis.** El aislamiento multi-tenant depende de una variable de sesión que fija la aplicación antes de cada consulta. El mismo rol que ejecuta las consultas puede cambiarla: `set_config()` es una función SQL corriente, y PostgreSQL no ofrece forma de impedir que un rol fije una variable personalizada (`app.*`). Una sentencia inyectada puede, por tanto, reescribir el tenant a mitad de ejecución y leer los datos de otro.

RLS deja así de ser una segunda barrera: solo aísla mientras no haya inyección SQL. Es la premisa que `SEC-03` daba por buena, y es falsa.

**Evidencia.** Contra Postgres real, conectado como `app_user` (sin `SUPERUSER` ni `BYPASSRLS` y con `FORCE ROW LEVEL SECURITY`), se ejecutó la versión anterior de `retrieve_subgraph` con un tokenizador que dejaba pasar comillas. La conexión era la de un tenant sin tripletas, y la palabra inyectada fue:

```
zzqx%' or true union select source_node, relation, target_node from (select set_config('app.current_tenant', '11111111-1111-1111-1111-111111111111', false)) s, knowledge_graph --
```

Devolvió **10 tripletas del otro tenant**. El `FROM` de la segunda rama ejecuta `set_config` antes de recorrer `knowledge_graph`, y la política evalúa `current_setting` fila a fila, así que ya lee el tenant reescrito. Con el código corregido, el mismo payload devuelve 0 filas.

**Por qué 🟠 y no 🔴.** Hoy no hay vector de entrada. `SEC-02` y `SEC-03` cerraron las dos inyecciones conocidas, y las demás consultas usan parámetros. Es una defensa en profundidad ausente, no una vulnerabilidad explotable ahora; pero convierte cualquier inyección futura en fuga entre tenants.

**Reproducción.** La sentencia equivalente a la verificada, como `app_user`:

```sql
SELECT set_config('app.current_tenant', '00000000-0000-0000-0000-000000000000', false);
SELECT count(*) FROM knowledge_graph;                  -- 0: el tenant no tiene tripletas
SELECT source_node, relation, target_node FROM knowledge_graph WHERE source_node ILIKE '%zzqx%' OR true
UNION SELECT source_node, relation, target_node
FROM (SELECT set_config('app.current_tenant', '11111111-1111-1111-1111-111111111111', false)) s, knowledge_graph
LIMIT 10;                                              -- filas del otro tenant
```

**Parche.** Requiere una decisión de diseño; no hay una línea que lo arregle.

1. **Contexto firmado.** La aplicación fija el tenant junto a una firma HMAC. Las políticas llaman a una función `SECURITY DEFINER` que verifica la firma con una clave guardada en una tabla que `app_user` no puede leer. Una inyección puede cambiar el tenant, pero no firmarlo.
2. **Un rol por tenant.** Las políticas usan `current_user`, y las credenciales de cada rol no están al alcance de SQL. Obliga a un pool por rol. Un `SET ROLE` desde un rol base miembro de todos no sirve, porque también está al alcance de una inyección.
3. **Cero SQL dinámico como regla comprobada.** Un test o linter que falle ante interpolación en `execute`/`fetch`. No corrige el diseño; reduce la probabilidad de que aparezca un vector.

Conviene decidirlo junto a `PERF-01`: los dos cambian cómo recibe cada conexión su tenant (`set_config` local a una transacción).

**Estado:** ✅ corregido el 2026-09-15 con la **opción 1, contexto firmado** (decisión del usuario).

`tenant_connection()` (`src/services/db.py`) fija ahora dos variables locales a la transacción: `app.current_tenant` y `app.tenant_signature`, esta última el HMAC-SHA256 del tenant con la clave de `TENANT_SIGNING_KEY`. Las cinco políticas dejan de leer `current_setting` y llaman a `app_current_tenant()`, función `SECURITY DEFINER`, `STABLE`, propiedad de `postgres` y con `search_path` fijo, que solo devuelve el tenant si la firma cuadra con la clave de `tenant_security.signing_key`. Una sentencia inyectada puede reescribir ambas variables, pero no firmarlas: la función devuelve `NULL` y no hay fila visible.

Verificación como `app_user` contra la BD real, con el payload del hallazgo:

| Caso | Antes | Después |
|---|:---:|:---:|
| Contexto legítimo (tenant con 128 tripletas) | 128 | 128 |
| Tenant reescrito por inyección (el payload de arriba) | **10** | **0** |
| Contexto sin firma (lo que enviaba el código anterior) | 128 | 0 |
| Contexto con firma inventada | — | 0 |
| `app_user` lee la clave de firma | — | `permission denied for schema tenant_security` |

Contra la API real, con la misma pregunta y el caché purgado entre fases: con la clave correcta, 4 fuentes y confianza 0,95; con una clave equivocada, 0 fuentes y *"No hay información disponible en el contexto proporcionado"*. La firma es lo único que cambia entre las dos fases, así que es ella la que sostiene el aislamiento.

**Coste medido.** El temor era que el HMAC se evaluase fila a fila. No ocurre: el plan mete la función como `Index Cond`, y `pg_stat_user_functions` cuenta **2 llamadas por consulta** tanto en un escaneo de 25.000 filas como en cinco consultas seguidas (10 llamadas). Es coste constante, no proporcional a las filas: sobre 50.000 filas sembradas, 30 escaneos completos pasan de 54 ms a 69–71 ms (~0,5 ms por consulta, medido dos veces alternando la política para descartar el orden).

**Arranque.** La clave la comparten la aplicación (`.env`) y la base (`sql/01_init.sql` la siembra vía `\getenv`, y `sql/migrations/apply_tenant_signing.sql` hace lo mismo sobre una base existente). Sin ella nadie arranca a medias: `docker compose` se niega a interpolar, el script de inicialización aborta con mensaje legible —y el contenedor sale, como en `BUG-04`— y la API levanta `RuntimeError` al importar `db.py`.

---

### `SEC-06` 🟡 Las respuestas de error devuelven el texto de la excepción

> Posterior a la foto: encontrado el 2026-09-14 al verificar `SEC-04` y `BUG-02`.

**Ubicación.** Tres puntos:

| Archivo:línea | Forma |
|---|---|
| `src/api/routers/ingest.py:39` | `raise HTTPException(status_code=500, detail=str(e))` |
| `src/api/routers/chat.py:96` | `raise HTTPException(status_code=500, detail=str(e))` |
| `src/api/routers/chat.py:182` | `yield f"data: {json.dumps({'error': str(e)})}\n\n"` |

**Análisis.** Cualquier excepción interna llega literal al cliente: rutas del sistema de archivos del servidor, mensajes de Postgres o detalles de configuración del SDK de Anthropic. Da información útil para preparar un ataque. Requiere estar autenticado.

**Evidencia.**
- Verificando `SEC-04`, el 500 de `/ingest/` devolvió `{"detail": "/var/folders/v2/n7jcjy_11cscqrgkctpn931c0000gn/T/cv.txt"}`.
- Verificando `BUG-02`, con el cliente de Anthropic sin clave, `/chat/stream/` entregó *"Could not resolve authentication method. Expected either api_key or auth_token to be set…"* en el evento de error.

**Reproducción.**

```bash
grep -rn "str(e)" src/api      # ingest.py:39, chat.py:96, chat.py:182
```

**Parche.** Registrar la excepción en el servidor y devolver un mensaje genérico con un identificador para correlacionarlo:

```python
except Exception:
    error_id = uuid.uuid4().hex[:8]
    logger.exception("Fallo en /ingest/ [%s]", error_id)
    raise HTTPException(status_code=500, detail=f"Error interno ({error_id})")
```

Los `HTTPException` con 400 o 422 son mensajes pensados para el cliente y se quedan igual. En `chat_endpoint`, el `except Exception` también captura y reenvuelve el `HTTPException` que el propio bloque lanza cuando el grafo no devuelve respuesta. Conviene dejar pasar `HTTPException` antes del caso genérico.

**Estado:** ✅ corregido el 2026-09-15.

Los tres puntos registran la excepción con `logger.exception` —el proyecto no usaba `logging` en ninguna parte; es su primer uso, y convive con los `print` del resto— y devuelven al cliente `Error interno (<id>)` con ocho caracteres hexadecimales. La clave `error` del evento SSE se mantiene, porque es la que renderiza `src/frontend/app.py:112`, igual que `detail` para la línea 53.

Verificación contra servidor real, forzando fallos de verdad (clave de Anthropic inválida y un PDF corrupto):

| Punto | Antes recibía el cliente | Después |
|---|---|---|
| `POST /chat/` | `Error code: 401 - {'type': 'error', ... 'message': 'API key is invalid.'}` | `Error interno (a85a8af2)` |
| `POST /chat/stream/` | el mismo 401, dentro de un HTTP 200 | `Error interno (e1942c67)` |
| `POST /ingest/` | `Failed to open file '/var/folders/v2/n7jcjy_.../tmp_f3a0h9w.pdf' as type pdf.` | `Error interno (81fa55bd)` |

Los tres identificadores aparecen exactamente una vez en el log del servidor, cada uno junto a su traza completa (`ERROR:src.api.routers.chat:Fallo en POST /chat/ [a85a8af2]`), y la ruta del temporal ya solo existe ahí. `grep -rn "str(e)" src/api` no devuelve nada.

Lo que no debía cambiar, comprobado aparte: el 400 de extensión no permitida llega íntegro (`Extensión no permitida. Soportadas: {...}`), y el 500 propio del router conserva su mensaje (`El Grafo de Agentes no devolvió una respuesta final.`) gracias al `except HTTPException: raise` que ahora precede al genérico. Este segundo caso vive entero en el router, así que se provocó sustituyendo el grafo por un doble que devuelve un estado sin `final_answer`.

---

## 5. Defectos Funcionales

### `BUG-01` 🟠 Caché envenenado con el prefijo de progreso

**Ubicación.** `src/api/routers/chat.py:100-123`

**Análisis.** El generador SSE acumula los mensajes de progreso de cada nodo en una única variable de texto:

```python
accumulated_answer = ""
...
    if node_name == "supervisor":
        accumulated_answer += "🤖 *Supervisor evaluando estrategia...*\n\n"
    elif node_name == "researcher":
        accumulated_answer += "🔍 *Investigador buscando en Postgres Vector y GraphRAG...*\n\n"
    elif node_name == "generator":
        accumulated_answer += "✍️ *Redactor estructurando respuesta final...*\n\n---\n\n"
```

Al llegar la respuesta real, la **concatena sobre el acumulado** y persiste ese mismo diccionario:

```python
final_dict = state_update["final_answer"].model_dump()
final_dict["answer"] = accumulated_answer + (final_dict.get("answer") or "")   # ← l. 119
yield f"data: {json.dumps(final_dict)}\n\n"
...
if final_dict:
    await save_semantic_cache(current_user.tenant_id, request.query, final_dict)   # ← l. 123
```

El propósito de la concatenación es correcto para el stream (el frontend calcula diffs de caracteres en `app.py:119-122`, así que la respuesta debe llegar como continuación del texto ya emitido). El error es **reutilizar ese objeto para la persistencia**.

**Contenido real de una fila de caché.**

```
🤖 *Supervisor evaluando estrategia...*

🔍 *Investigador buscando en Postgres Vector y GraphRAG...*

✍️ *Redactor estructurando respuesta final...*

---

Bryan tiene experiencia en arquitecturas cloud sobre AWS...
```

**Degradación acumulativa.** En el siguiente hit, `chat.py:79` antepone otro marcador:

```python
cached_data["answer"] = "⚡ [CACHE HIT] " + cached_data.get("answer", "")
```

resultando en `⚡ [CACHE HIT] 🤖 *Supervisor evaluando…* 🔍 *Investigador…* ✍️ *Redactor…* --- <respuesta>`. El usuario ve una traza de ejecución **que no ocurrió** —el grafo no se ejecutó, fue un hit de caché— describiendo pasos que el sistema se saltó.

**Impacto colateral en el evaluador.** La línea 127 pasa `final_dict.get("answer", "")` —ya contaminado— a `evaluate_rag_response`. El juez LLM evalúa *faithfulness* sobre un texto que empieza con tres líneas de metadatos de UI ausentes del contexto recuperado. Es ruido sistemático que sesga a la baja la métrica que `README.md` §4 presenta como observabilidad activa.

**Asimetría entre endpoints.** El endpoint síncrono `/chat/` (l. 56) cachea correctamente `structured_response.model_dump()` sin contaminar. Solo el endpoint SSE —el que usa el frontend— está afectado. Eso explica que el defecto haya pasado desapercibido si las pruebas se hicieron contra `/chat/`.

**Reproducción.**

```bash
sed -n '112,124p' src/api/routers/chat.py
```

Sobre una base existente, para medir el alcance:

```sql
SELECT count(*) FROM semantic_cache WHERE response_json->>'answer' LIKE '%Supervisor evaluando%';
```

**Parche.** Separar el objeto que se emite del que se persiste:

```diff
                         if "final_answer" in state_update and state_update["final_answer"]:
-                            final_dict = state_update["final_answer"].model_dump()
-                            # Anexamos la respuesta final real
-                            final_dict["answer"] = accumulated_answer + (final_dict.get("answer") or "")
-                            yield f"data: {json.dumps(final_dict)}\n\n"
+                            # Objeto limpio: es el que se cachea y se evalúa.
+                            final_dict = state_update["final_answer"].model_dump()
+                            # Objeto para el stream: continúa el texto ya emitido al cliente.
+                            stream_dict = {
+                                **final_dict,
+                                "answer": accumulated_answer + (final_dict.get("answer") or ""),
+                            }
+                            yield f"data: {json.dumps(stream_dict)}\n\n"
```

Con eso, `save_semantic_cache` (l. 123) y `evaluate_rag_response` (l. 127) reciben ya el objeto limpio sin más cambios.

**Limpieza de datos existentes.** Prerrequisito: el arreglo impide generar filas nuevas contaminadas, pero las existentes se siguen sirviendo. Conviene anclar el patrón al **inicio** de la cadena —la contaminación siempre es un prefijo— para no borrar una respuesta legítima que mencione el Supervisor a mitad de texto:

```sql
DELETE FROM semantic_cache
WHERE response_json->>'answer' LIKE '🤖 *Supervisor evaluando estrategia...*%';
```

Debe ejecutarse como `postgres`: bajo RLS, `app_user` solo ve las filas de un tenant por sesión.

**Estado: ✅ corregido (2026-09-11).** Separado `stream_dict` (con progreso, para el SSE) de `final_dict` (limpio, para caché y evaluador). Verificado end-to-end con el grafo mockeado: el último evento SSE conserva el prefijo de progreso —el frontend sigue renderizando diffs correctamente— mientras que el objeto persistido y el texto enviado al juez empiezan por la respuesta real, con `confidence_score` y `sources` intactos.

**Daño encontrado en la base auditada:** 4 de 8 filas de `semantic_cache` contaminadas (50 %), todas procedentes del endpoint SSE; las 4 limpias venían del endpoint síncrono. Purgadas con la consulta anclada de arriba.

---

### `BUG-02` 🟠 El caché intercepta las ejecuciones de herramientas

**Ubicación.** `src/api/routers/chat.py:26-29` (síncrono) y `:77-81` (SSE)

```python
cached_data = await check_semantic_cache(current_user.tenant_id, request.query)
if cached_data:
    return StructuredAnswer(**cached_data)
```

**Análisis.** El caché se consulta **antes** de que el supervisor clasifique la intención, y el guardado (l. 56 y l. 123) tampoco consulta el `intent_type` resultante. Todas las respuestas se cachean por igual, sean deterministas o no.

**Precisión sobre el alcance (verificada al corregir `BUG-01`).** Los dos endpoints no se comportan igual:

- **`/chat/` (síncrono, l. 56)** cachea de forma incondicional, incluidas las respuestas de `tool_execution`. Aquí el defecto se manifiesta completo.
- **`/chat/stream/` (SSE, l. 123)** solo asigna `final_dict` dentro de la rama `elif node_name == "generator"`. Cuando el supervisor resuelve por sí mismo (saludo, herramienta, `out_of_scope`), `route_supervisor` va directo a `END`, el nodo generador nunca se ejecuta y `final_dict` queda en `None`: **no se guarda nada**.

Como el frontend usa el endpoint SSE, en la práctica los resultados de herramientas no se están cacheando hoy —lo confirma la base auditada, sin una sola fila de herramienta—. Pero el defecto sigue siendo real por dos vías: `/chat/` sí los persiste, y la **lectura** del caché (l. 27 y l. 77) ocurre en ambos endpoints, de modo que una fila guardada vía `/chat/` se sirve después a los usuarios del stream. La corrección de abajo cubre los dos caminos.

El problema es que tres de las cuatro intenciones producen respuestas **inherentemente no cacheables**:

| Intención | Cacheable | Motivo |
|---|:---:|---|
| `knowledge_search` | ✅ | Determinista mientras no cambie el corpus |
| `casual_greeting` | ✅ | Inocuo |
| `tool_execution` | ❌ | El valor cambia en cada invocación, por definición |
| `out_of_scope` | ⚠️ | Inocuo, pero desperdicia espacio de índice |

**Escenario concreto.** Con umbral de similitud 0.85 (`cache.py:16`):

1. `10:00` — Usuario: *"¿Qué hora es?"* → `tool_execution` → `get_current_time()` → *"La fecha y hora actual es: 2026-09-10 10:00:00"*. Se cachea.
2. `14:30` — Usuario: *"¿me dices la hora?"* → similitud ≈ 0.88 sobre 0.85 → **cache hit** → *"⚡ [CACHE HIT] … 10:00:00"*.
3. Al día siguiente, y de forma indefinida: la misma respuesta. La tabla `semantic_cache` no tiene política de expiración (`ROADMAP_FASE_5_ESCALABILIDAD.md` §3 lo identifica correctamente como trabajo futuro), así que la entrada es perpetua.

Lo mismo con `get_crypto_price` (un precio de Bitcoin congelado servido como actual) y `get_github_profile` (contador de repos y seguidores obsoleto).

**Impacto documental.** `README.md` §1 presenta las herramientas como *"Herramientas Externas (Function Calling): El supervisor puede desviar la consulta para invocar APIs externas de forma determinista"*. `PAPER.md` §6.5 y `PAPER_PLAN.md` §2 documentan las tres. Ninguna de las tres funciona correctamente más de una vez.

**Reproducción.**

```bash
grep -n "check_semantic_cache\|save_semantic_cache\|intent_type" src/api/routers/chat.py
# 27, 56, 77, 123 → ninguna referencia a intent_type
```

**Parche.** Condicionar el guardado al `intent_type` del estado final. Endpoint síncrono:

```diff
+NON_CACHEABLE_INTENTS = {"tool_execution", "out_of_scope"}
+
@@
-        await save_semantic_cache(current_user.tenant_id, request.query, structured_response.model_dump())
+        if (final_state.get("intent_type") not in NON_CACHEABLE_INTENTS
+                and not structured_response.requires_more_info
+                and structured_response.confidence_score >= 0.5):
+            await save_semantic_cache(current_user.tenant_id, request.query, structured_response.model_dump())
```

Endpoint SSE: capturar `intent_type` del `state_update` del supervisor (que ya se recorre en l. 104) y aplicar la misma condición antes de la l. 123.

Las dos condiciones adicionales evitan otro problema latente: hoy se cachea igualmente una respuesta con `requires_more_info=True` o `confidence_score=0.2` —es decir, se fija permanentemente una respuesta que el propio sistema considera insuficiente.

**Estado: ✅ corregido (2026-09-14).** Los dos endpoints guardan en caché solo si `is_cacheable(intent_type, respuesta)` lo permite: la intención está en la lista blanca `{knowledge_search, casual_greeting}`, `requires_more_info` es falso y `confidence_score ≥ 0,5`. El stream toma `intent_type` del `state_update` del supervisor. Tres diferencias con el parche de arriba:

- **Lista blanca en vez de lista negra.** `QueryIntent.intent_type` es un `str` libre que rellena el LLM, y con lista negra cualquier valor inesperado se cachearía.
- **Cambió el alcance.** La precisión de arriba ya no vale: al corregir `BUG-09` (2026-09-13), `/chat/stream/` pasó a recoger también la respuesta del supervisor, y desde entonces cacheaba herramientas y `out_of_scope` igual que `/chat/`.
- **El daño era mayor.** No se limitaba a datos viejos: servía datos de **otra consulta**. Medido con el modelo real (`all-MiniLM-L6-v2`, umbral 0,85):

| Par de consultas | Similitud | ¿Hit? |
|---|:---:|:---:|
| `¿Cuánto vale bitcoin?` ↔ `¿Cuánto vale ethereum?` | 0,886 | sí |
| `¿Cuál es la capital de Francia?` ↔ `¿Cuál es la capital de Chile?` | 0,860 | sí |
| `¿Qué hora es?` ↔ `¿me dices la hora?` | 0,815 | no |
| `Hola` ↔ `Hola, ¿qué hora es?` | 0,535 | no |

Los saludos no colisionan con peticiones que empiezan por "Hola" (0,28–0,67 en los pares medidos), y por eso siguen siendo cacheables.

Verificado contra uvicorn real, con el grafo, el LLM y Postgres de verdad, como el tenant sin filas en caché. `analyze_query` se envolvió solo para registrar la intención, sin alterar el resultado. El oráculo: una respuesta del grafo escribe fila en `semantic_cache` si y solo si la política lo permite.

| Escenario | Antes | Después |
|---|---|---|
| `¿Qué hora es?` dos veces, `/chat/` | Hit: `12:58:15` las dos veces | `13:00:58` → `13:01:02`, sin fila |
| `¿Qué hora es?` dos veces, `/chat/stream/` | Hit: `12:58:19` las dos veces | `13:01:03` → `13:01:07`, sin fila |
| Bitcoin y después ethereum | Hit: *"El precio actual de Bitcoin es $78593 USD"* | *"El precio actual de Ethereum es $2507.41 USD"* |
| Francia y después Chile (`out_of_scope`) | Hit con la respuesta de Francia | Respuesta propia, sin fila |
| Saludo | Se cachea | Se cachea |
| Conocimiento repetido (control positivo) | Hit | Hit |
| Filas escritas contra la política | 4 | 0 (10 respuestas evaluadas) |
| **Comprobaciones** | **3/8** | **8/8** |

Aparte, 11 casos límite de `is_cacheable` que el LLM no produce a voluntad: `requires_more_info=True`, confianza 0,49 / 0,5 / `None`, intención con otra capitalización, vacía o `None`. Todos correctos. La base se devolvió a su estado inicial, esperando a que terminaran los background tasks.

**Pendiente.** Una fila de la base auditada no pasaría la política (`requires_more_info=true`, confianza 0,75) y se sigue sirviendo: es la decisión de datos D-02 de la tabla de remediación. El caché tampoco tiene en cuenta el historial, porque el texto de una pregunta de seguimiento (*"¿Y en qué años?"*) no basta como clave: catalogado como `BUG-10`.

---

### `BUG-03` 🟠 El historial de conversación se descarta

**Ubicación.** `src/services/agent_graph/nodes.py:18`

```python
intent = await analyze_query(state["query"], [])
```

**Análisis.** La cadena de custodia del historial se rompe en el último eslabón. Recorrido completo:

| Paso | Ubicación | Estado |
|---|---|:---:|
| El frontend construye el historial | `src/frontend/app.py:87` | ✅ |
| Lo envía en el payload | `src/frontend/app.py:88` | ✅ |
| `ChatRequest` lo declara y valida | `src/models/requests.py:6` | ✅ |
| El endpoint recibe `request.history` | `chat.py:24`, `:70` | ✅ |
| Se copia al `AgentState` | — | ❌ **roto** |
| `supervisor_node` lo pasa a `analyze_query` | `nodes.py:18` | ❌ recibe `[]` |

`AgentState` (`state.py:7-28`) no tiene campo `history`. Su campo `messages` —declarado con reductor `operator.add` para acumulación (l. 9)— se inicializa como `[]` en `chat.py:36` y `:86` y **nunca se escribe**: ningún nodo devuelve `messages` en su diccionario de retorno.

**Qué código queda inalcanzable.** `analyze_query` implementa el formateo de historial completo (`router.py:40-46`):

```python
history_str = ""
if history:
    recent_history = history[-4:]      # ventana de 4 mensajes para acotar tokens
    history_str = "Historial reciente de la conversación:\n"
    for msg in recent_history:
        history_str += f"- {msg['role'].upper()}: {msg['content']}\n"
```

Con `history=[]`, `history_str` queda vacío y se interpola como cadena vacía en el prompt (l. 54). Y la instrucción del prompt (`router.py:68`):

> *"Si la pregunta depende de historial (ej: '¿Y qué hizo ahí?'), resuelve la correferencia en todas las variaciones."*

no tiene ningún dato sobre el que operar.

**Impacto funcional.** Toda pregunta de seguimiento se procesa como si fuera la primera de la conversación:

- *"¿Qué experiencia tiene Bryan en AWS?"* → funciona.
- *"¿Y en qué años?"* → el supervisor no sabe a qué se refiere "y en qué años". En el mejor caso genera variantes Multi-Query genéricas y recupera contexto irrelevante; en el peor lo clasifica como `out_of_scope`.

El caso *"¿Y qué hizo ahí?"* que el prompt usa como ejemplo canónico es precisamente el que falla.

**Impacto documental.** `PAPER.md` §4.3.1 describe al supervisor resolviendo correferencias como capacidad activa. El docstring de `analyze_query` (`router.py:38`) dice: *"Analiza la intención del usuario y resuelve correferencias usando el historial"*.

**Reproducción.**

```bash
grep -rn "history" src/ | grep -v "^src/frontend"
# src/models/requests.py:6  → declarado
# src/services/router.py:36,40-46 → consumido
# ninguna línea conecta ambos
```

**Parche.** Tres cambios pequeños.

1. `src/services/agent_graph/state.py`:

```diff
 class AgentState(TypedDict):
     messages: Annotated[Sequence[BaseMessage], operator.add]
     tenant_id: str
     user_profile: str
     query: str
+    history: List[Dict[str, str]]
```

2. `src/api/routers/chat.py`, en ambos `initial_state` (l. 35 y l. 85):

```diff
             query=request.query,
+            history=request.history,
             intent_type="",
```

3. `src/services/agent_graph/nodes.py:18`:

```diff
-    intent = await analyze_query(state["query"], [])
+    intent = await analyze_query(state["query"], state.get("history", []))
```

La ventana de 4 mensajes de `router.py:41` ya acota el coste en tokens, así que no hace falta más control.

**Estado: ✅ corregido (2026-09-11).** Los tres cambios aplicados, más un endurecimiento de `analyze_query`: el historial lo envía el cliente, así que un turno sin `role`/`content` —o que no sea un diccionario— se descarta en lugar de tumbar la petición con un `KeyError`.

Verificado en cinco fases, con el contraste *con historial* / *sin historial* como control:

| Fase | Qué comprueba | Resultado |
|:---:|---|---|
| 1 | El historial se interpola en el prompt del router; la ventana recorta a los 4 últimos turnos; sin historial no se inyecta un bloque vacío | ✅ |
| 2 | Payload malformado (turno sin `role`, sin `content`, no-dict, `content` vacío, `None`): ninguna excepción, y el turno válido de una mezcla sobrevive | ✅ |
| 3 | Cadena de custodia `AgentState` → `supervisor_node` → `analyze_query`: recibe los 2 turnos intactos; un estado sin la clave degrada a `[]` sin `KeyError` | ✅ |
| 4 | Correferencia real contra la API: *"¿Y en qué años?"* tras hablar de Betterfly → las 3 variaciones Multi-Query citan Betterfly. Sin historial → 3 variaciones genéricas sobre la cronología completa | ✅ |
| 5 | End-to-end HTTP (`POST /auth/token` → `POST /chat/` y `/chat/stream`) contra el grafo y la BD reales, espiando `retrieve_documents` | ✅ |

La fase 5 mide en el límite real de la búsqueda —qué texto se interroga contra Postgres— porque es ahí donde se observa el efecto:

```
CON historial (4/4 consultas resuelven la correferencia):
  · ¿En qué años trabajó Bryan Bobadilla en Betterfly?
  · Período de empleo años Betterfly Bryan Bobadilla
  · Fechas de trabajo experiencia Betterfly ingeniero
  · [HyDE] Bryan Bobadilla se desempeñó como Ingeniero de Software Senior Back End en Betterfly…

SIN historial (0/4), misma pregunta literal:
  · ¿En qué años trabajó Bryan Bobadilla en sus experiencias profesionales?
  · Años de experiencia y timeline laboral de Bryan Bobadilla
  · ¿Cuál es el periodo temporal o rango de años de las posiciones de Bryan Bobadilla?
  · [HyDE] Bryan Bobadilla ha tenido una trayectoria profesional que abarca desde 2015 hasta 2023…
```

Ambos endpoints quedan cubiertos: `/chat/` y `/chat/stream` propagan el historial por igual. Hubo que purgar el caché semántico entre fases, porque si no la segunda pregunta es un *cache hit* de la primera y el control negativo deja de ser válido —una consecuencia directa de `BUG-02`—. La base de datos quedó en su estado inicial (4 filas de `semantic_cache`, 3 de `user_memory`, 0 de `rag_evaluations`).

**Derivado, ya cerrado: el redactor tampoco veía el historial.** La corrección de arriba reconecta el historial con el **supervisor**, que es donde el defecto estaba localizado, y con ello la recuperación pasa a ser la correcta. Pero al verificarlo se vio que `generator_node` (`nodes.py:105`) invocaba `generate_answer(query=state["query"], …)` con la pregunta cruda, así que el redactor recibía el contexto correcto sin saber a qué se refería *"y"*, y respondía enumerando la cronología completa del CV —los mismos 11 años con y sin historial— en lugar de acotarse al período de Betterfly. Recuperar lo correcto estaba resuelto; redactar sobre el referente correcto, no.

Se cerró propagando `history` también a `generate_answer`, con una instrucción explícita en su prompt para resolver la correferencia y no volcar el contexto sobrante. De paso, el formateo del historial —ventana de 4 turnos y descarte de turnos malformados— se extrajo a `src/services/history.py`, porque router y redactor deben aplicar exactamente las mismas reglas y tenerlas duplicadas es la forma en que vuelven a divergir.

El efecto sobre la respuesta final, misma pregunta literal:

| | Respuesta a *"¿Y en qué años?"* | Años citados |
|---|---|:---:|
| Antes | Volcado de la cronología completa del CV (1.039–1.202 caracteres) | 11 |
| Después, **con** historial | *"Bryan trabajó en Betterfly como Ingeniero de Software Senior – Back End desde **Abril 2024 hasta el presente**."* (111 caracteres) | 1 |
| Después, **sin** historial (control) | *"No puedo responder… es una pregunta de seguimiento que depende de una pregunta previa… Por favor, clarifica cuál es el tema."* | 0 |

El control mejora por partida doble: sin historial el sistema ya no inventa una respuesta plausible volcando todo lo que recuperó, sino que declara que le falta el referente y pide la aclaración. Las 13 comprobaciones de recuperación y redacción pasan en las dos corridas, y la base de datos vuelve a su estado inicial en ambas.

`generate_answer_stream` (`extractor.py:56`) no se tocó: es código muerto desde la migración a LangGraph y su destino se decide en `DOC-01`.

---

### `BUG-04` 🟠 Bootstrap de Docker roto por orden de scripts SQL

**Ubicación.** `docker-compose.yml:9-10`

```yaml
    volumes:
      - ./sql:/docker-entrypoint-initdb.d
```

**Análisis.** El *entrypoint* de la imagen oficial de PostgreSQL ejecuta todos los `.sql` de ese directorio **en orden alfabético** sobre un volumen vacío. Orden resultante:

```
1. 01_init.sql
2. apply_cache.sql
3. apply_evaluator.sql
4. apply_graphrag.sql
5. apply_memory.sql
6. apply_rls.sql
7. create_app_user.sql      ← crea el rol app_user
```

Los cuatro `apply_*.sql` de tablas terminan con un `GRANT`:

```sql
GRANT ALL PRIVILEGES ON TABLE semantic_cache TO app_user;     -- apply_cache.sql:20
GRANT ALL PRIVILEGES ON TABLE rag_evaluations TO app_user;    -- apply_evaluator.sql:19
GRANT ALL PRIVILEGES ON TABLE knowledge_graph TO app_user;    -- apply_graphrag.sql:21
GRANT ALL PRIVILEGES ON TABLE user_memory TO app_user;        -- apply_memory.sql:20
```

pero `app_user` no existe hasta el paso 7.

**Fallo observado.** Un `docker compose up -d` sobre volumen limpio aborta en el paso 2:

```
ERROR:  role "app_user" does not exist
```

El entrypoint de la imagen oficial trata los errores de inicialización como fatales: el contenedor termina y la base queda con `01_init.sql` aplicado y nada más.

**Por qué no se detectó.** `PAPER_PLAN.md` §1 describe los `apply_*.sql` como *"scripts individuales de migración iterativa usados durante el desarrollo"*. Se ejecutaron a mano, en orden lógico, sobre una base ya existente donde `app_user` ya estaba creado. El fallo solo aparece en un entorno nuevo — es decir, para cualquiera que clone el repositorio.

**Dos huecos asociados en el mismo punto.**

1. **`01_init.sql` no crea `knowledge_graph`.** La tabla solo existe en `apply_graphrag.sql`. Si se corrigiera el orden ejecutando únicamente `01_init.sql`, el GraphRAG fallaría en tiempo de ejecución con `relation "knowledge_graph" does not exist`. `PAPER_PLAN.md` §1 lo describe como *"script unificado para crear tablas"* — no lo es.

2. **`01_init.sql` no aplica `FORCE ROW LEVEL SECURITY`.** Las cuatro tablas obtienen `ENABLE ROW LEVEL SECURITY`, pero sin `FORCE` **el propietario de la tabla elude sus propias políticas**. Solo `create_app_user.sql:6` aplica `FORCE`, y únicamente a `documents`. Las demás dependen de sus respectivos `apply_*.sql` —los que fallan—. Combinado con el DSN de `.env.example` (usuario `postgres`, propietario de todo), el aislamiento multi-tenant queda **desactivado de facto**. Ver `DOC-03`.

**Reproducción.**

```bash
ls sql/ | sort
grep -n "app_user" sql/*.sql
grep -c "FORCE ROW LEVEL SECURITY" sql/01_init.sql   # 0
grep -n "knowledge_graph" sql/01_init.sql            # sin coincidencias
```

**Parche.** Renombrar con prefijo numérico que refleje las dependencias reales:

```
00_create_app_user.sql     (antes create_app_user.sql, sin el ALTER TABLE documents)
01_init.sql                (+ knowledge_graph, + FORCE en las 5 tablas, + GRANTs)
02_migrations/             (los apply_*.sql, fuera del initdb: son histórico de migración)
```

`create_app_user.sql` debe perder su última línea (`ALTER TABLE documents FORCE ROW LEVEL SECURITY`), que hace referencia a una tabla que aún no existe si el rol se crea primero. Ese `FORCE` pertenece a `01_init.sql`, junto a los de las otras cuatro tablas.

Añadir además a `docker-compose.yml` el healthcheck que `ROADMAP_FASE_5_ESCALABILIDAD.md` §1 ya contempla, para que el fallo de inicialización sea visible:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
```

**Estado: ✅ corregido (2026-09-14).** La estructura queda como propone el parche: `00_create_app_user.sql` sin su `ALTER TABLE`, un `01_init.sql` completo y los `apply_*.sql` en `sql/migrations/` (el entrypoint ignora los subdirectorios). Hay cuatro ajustes:

- **`01_init.sql` reproduce exactamente la base de desarrollo**, que es contra la que funciona la aplicación. Incluye `knowledge_graph`, `FORCE` en las cinco tablas y los `GRANT`, y además crea los índices **con los nombres que tienen en desarrollo**. Los `apply_*.sql` creaban índices con nombre y el `01_init.sql` anterior los creaba sin él, así que ejecutar ambos habría duplicado cada índice HNSW.
- **Healthcheck por TCP** (`pg_isready -h 127.0.0.1`) y no por socket, como tenía el parche. El entrypoint arranca el servidor temporal de inicialización con `-c listen_addresses=''` (`docker-entrypoint.sh:297`). Por socket respondería mientras corren los scripts; por TCP, solo cuando han terminado.
- **Corrección al punto 2.** `FORCE` no rescata el DSN de `.env.example`. `postgres` es superusuario, y un superusuario elude RLS **con o sin `FORCE`** (verificado abajo). `FORCE` sí somete a las políticas a un propietario que no sea superusuario. El aislamiento exige que la aplicación conecte como `app_user`, lo que sigue pendiente en `DOC-03`.
- **Referencias actualizadas** en `PAPER_PLAN.md`, `GRAPHRAG_ARCHITECTURE.md`, `PAPER.md` y `PAPER_EN.md`. La cita *"`01_init.sql`, líneas 42-44"* de los papers ya era incorrecta antes del cambio: apuntaba a la política del caché, no a los `CHECK` de `rag_evaluations`.

Verificado con el `docker-compose.yml` real, con otro nombre de proyecto y otro puerto mediante un override, sobre volumen vacío y sin tocar la base de desarrollo:

| Prueba | Antes | Después |
|---|---|---|
| Arranque desde cero | El contenedor sale con `exit=3` a los 2 s: `apply_cache.sql:20: ERROR: role "app_user" does not exist` | `00_create_app_user.sql` → `01_init.sql`, `ignoring …/migrations`, `healthy` a los 5,3 s, sin errores. Reproducido dos veces |
| Huella del catálogo frente a la base de desarrollo: columnas (sin posición), índices, restricciones, políticas, RLS/`FORCE`, permisos y ACL | — | **Idéntica**: 77 de 77 líneas |
| RLS como `app_user` | — | 7/7. Cada tenant ve solo lo suyo, sin tenant no ve nada y la escritura cruzada se rechaza. El superusuario ve todo pese a `FORCE`, y un propietario no superusuario ve 0 filas con `FORCE` y 2 sin él |
| Aplicación real (ingesta + `/chat/`) contra la base nueva | — | 6/6. 1 fragmento y 7 tripletas ingeridos; la respuesta cita el documento con confianza 1,0; se escriben caché y evaluación bajo el tenant del token; la base de desarrollo sigue intacta |

Una observación de la última prueba: `rag_evaluations` recibió una fila. El evaluador no falla siempre: con un contexto de un solo documento, la respuesta del juez cabe en `max_tokens=300`. Con el contexto del corpus real no cabe (`PERF-04`), y por eso la base de desarrollo no tiene ninguna evaluación.

---

### `BUG-05` 🟡 El ciclo de auto-corrección no corrige nada

**Ubicación.** `src/services/agent_graph/graph.py:11-18`

```python
def route_reviewer(state: AgentState) -> str:
    # Si Claude indicó que requiere más info y no hemos iterado demasiado
    if state.get("needs_more_info") and state.get("iterations", 0) < 2:
        print("🔄 [Revisor] Falta contexto. Volviendo al Investigador con instrucciones extendidas...")
        # NOTA: En una implementación más avanzada, aquí modificaríamos 'search_queries'
        # para que busque algo más específico. Por ahora, solo re-itera.
        return "researcher"
    return "END"
```

**Análisis.** El mecanismo de decisión es correcto y está bien cableado: `generate_answer` devuelve `StructuredAnswer.requires_more_info`, `generator_node` lo mapea a `state["needs_more_info"]` (`nodes.py:115`), y `route_reviewer` lo lee. La guarda de iteraciones funciona: `researcher_node` incrementa el contador (`nodes.py:95`) y el límite de 2 previene bucles infinitos.

El problema es qué ocurre **después** de volver. `researcher_node` (`nodes.py:61-95`) lee `state["search_queries"]` —que ningún nodo ha modificado— y ejecuta:

```python
retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=15) for q in queries]
```

Las mismas consultas, contra la misma base de datos, con el mismo `top_k`. La búsqueda vectorial y el FTS son deterministas. El reranking es determinista. El resultado es **byte por byte idéntico** al de la primera iteración.

El generador recibe el mismo contexto, y al ser un LLM con temperatura por defecto (1.0, según `PAPER_PLAN.md` §3.4) hay una probabilidad no nula de que esta vez no marque `requires_more_info` — pero eso es ruido de muestreo, no corrección.

El mensaje impreso (*"Volviendo al Investigador con instrucciones extendidas"*) describe algo que no sucede: no hay instrucciones extendidas.

**Coste medido de una iteración estéril:**

| Recurso | Coste |
|---|:---:|
| Conexiones a Postgres | +6 (5 retrieval + 1 grafo) |
| Invocaciones a FlashRank | +1 (sobre ~75 candidatos) |
| Llamadas a Claude | +1 (generación completa, `max_tokens=8192`) |
| Latencia | ~2× la de una consulta normal |

**Impacto documental.** El comentario del código es honesto. `PAPER.md` §5.4, en cambio, lo formaliza como máquina de estados con *Self-Correction* funcional, y §4.3.3 describe al generador *"actuando conceptualmente como Reviewer"*. El `README.md` es el más explícito:

> *"Ciclos de Razonamiento: Si el Agente Redactor detecta que el contexto recuperado es insuficiente, rechaza la generación y devuelve el control al Investigador para hacer consultas más profundas."*

Las consultas no son más profundas: son las mismas.

**Reproducción.**

```bash
sed -n '11,18p' src/services/agent_graph/graph.py
sed -n '61,72p' src/services/agent_graph/nodes.py   # queries sin modificar
```

**Parche.** Dos opciones, y conviene elegir explícitamente.

**(a) Hacer que el ciclo aporte algo** — ampliar la búsqueda en cada reintento. Es el cambio mínimo con efecto real:

```diff
--- a/src/services/agent_graph/nodes.py
+++ b/src/services/agent_graph/nodes.py
@@ async def researcher_node(state: AgentState) -> dict:
     queries = state["search_queries"]
+    iteration = state.get("iterations", 0)
+    # En reintentos, ampliamos la ventana de recuperación y relajamos el reranking:
+    # el generador ya nos dijo que con el contexto estrecho no le bastaba.
+    retrieve_k = 15 + (15 * iteration)
+    rerank_k = 10 + (5 * iteration)

-    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=15) for q in queries]
+    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=retrieve_k) for q in queries]
@@
-    best_results = await rerank_documents(state["query"], unique_candidates, top_k=10)
+    best_results = await rerank_documents(state["query"], unique_candidates, top_k=rerank_k)
```

Más ambicioso: reinvocar `analyze_query` pidiendo variantes distintas, pasándole las ya intentadas como negativas.

**(b) Desactivar el ciclo y alinear la documentación** — si no se va a implementar (a), lo honesto es `iterations < 1` (nunca reitera) y reescribir el README y `PAPER.md` §5.4 describiendo el flag `requires_more_info` como lo que es: una señal de calidad reportada al usuario, no un mecanismo de corrección.

**Estado: ✅ corregido (2026-09-14), opción (a), elegida por el usuario.** `researcher_node` calcula su ventana con `retrieval_window(base_retrieve, base_rerank, iteración)`. Hay tres diferencias con el parche de arriba:

- **La base son los `top_k` del cliente**, que `BUG-06` hizo efectivos, y no un 15/10 fijo. Cada reintento multiplica los candidatos por variante y deja pasar un 50 % más de documentos, redondeando hacia arriba: 15/10 → 30/15, 15/3 → 30/5, 15/1 → 30/2. El techo son los máximos de la API (`MAX_TOP_K_RETRIEVE=50`, `MAX_TOP_K_RERANK=20`, ahora constantes en `requests.py`), así que el ciclo respeta la misma cota de coste que una petición.
- **No hay reintentos estériles.** El investigador marca `retrieval_exhausted` cuando una ventana mayor no puede cambiar el contexto: ninguna búsqueda llenó su cupo y el redactor ya recibió todos los candidatos, o la ventana siguiente es igual por los máximos. En ese caso `route_reviewer` termina aunque el redactor pida más información. Con corpus pequeños, como el de este sandbox (11 documentos por tenant), es el caso frecuente.
- **El mensaje dice lo que ocurre** (*"Volviendo al Investigador con la búsqueda ampliada"*), y el reintento imprime la ventana que usa. README, `PAPER_PLAN.md`, `PAPER.md` y `PAPER_EN.md` describen ahora la ampliación y la nueva condición de salida.

Verificado contra uvicorn real, con el grafo, el LLM y Postgres de verdad. Búsqueda, re-ranking y redactor se envolvieron solo para registrar, en cada pasada, la ventana, los documentos (con sus ID) y si el redactor pedía más información. Un `top_k_rerank` bajo provoca el reintento de forma fiable:

| Escenario | Antes | Después |
|---|---|---|
| Sin parámetros (control positivo) | 1 pasada, 15/10 | 1 pasada, 15/10 |
| `/chat/`, `top_k_rerank=1` | 2 pasadas **idénticas**: 15/1, mismo documento | 15/1 → **30/2**, 1 documento nuevo |
| `/chat/stream/`, `top_k_rerank=3` | 2 pasadas **idénticas**: 15/3, mismos documentos | 15/3 → **30/5**, 2 documentos nuevos |
| Pregunta sin respuesta en el corpus, contexto ya agotado (11 < 15 y 11 ≤ 20) | 2 pasadas idénticas | **1 pasada**: no reintenta |
| Algún reintento repite la búsqueda anterior | 3 de 3 | 0 |
| **Comprobaciones** | **3/7** | **7/7** |

Aparte, 18 casos directos sin base de datos ni LLM: la ventana (incluidos los topes 30/15 → 50/20 y 50/20 → 50/20), las cinco ramas de `route_reviewer` y el flag de agotamiento con corpus simulados de 11 y 100 documentos. La base se devolvió a su estado inicial.

**Límites de lo medido.** El reintento aporta contexto nuevo, pero no garantiza que el redactor quede satisfecho: en los dos escenarios con reintento volvió a pedir más información. Con este corpus, la ampliación de la búsqueda (15 → 30) no añadió candidatos, porque cada tenant tiene 11 documentos; los documentos nuevos salieron de ampliar el re-ranking. El efecto de la búsqueda con un corpus mayor está cubierto por los casos directos, no medido contra la base real. La alternativa más ambiciosa, reformular las consultas en el reintento, queda sin implementar.

---

### `BUG-06` 🟡 `top_k_retrieve` / `top_k_rerank` son decorativos

**Ubicación.** `src/models/requests.py:4-8` los declara como contrato público de la API:

```python
class ChatRequest(BaseModel):
    query: str
    history: List[Dict[str, str]] = Field(default_factory=list, ...)
    top_k_retrieve: int = 15
    top_k_rerank: int = 7
```

`src/services/agent_graph/nodes.py:70` y `:83` los ignoran:

```python
retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=15) for q in queries]
best_results = await rerank_documents(state["query"], unique_candidates, top_k=10)
```

**Análisis.** La API acepta ambos parámetros, Pydantic los valida, y se descartan en silencio. Un cliente que envíe `top_k_rerank: 3` recibe exactamente el mismo comportamiento que uno que envíe `top_k_rerank: 50`.

Nótese además que ni siquiera coinciden los valores: el contrato declara `top_k_rerank: int = 7` y el código usa `10`.

**Por qué importa más de lo que parece.** `TROUBLESHOOTING.md` §2 documenta un bug real —*"El Re-ranker omite información vital"*— y registra como parte de la solución:

> *"Ampliación del Context Window: Se modificó `src/models/requests.py` para aumentar `top_k_rerank` de 3 a 7."*

Esa solución documentada **hoy no tiene ningún efecto**. Si el problema reapareciera, alguien siguiendo el post-mortem ajustaría un valor inerte. Es peor que un parámetro ausente: es una palanca que parece funcionar.

(La otra mitad de la solución de §2 —la deduplicación por `content` y la ampliación a 15 candidatos— sí sobrevivió a la migración, en `nodes.py:74-80` y `:70`.)

**Reproducción.**

```bash
grep -rn "top_k_retrieve\|top_k_rerank" src/
# única coincidencia: src/models/requests.py:7-8 (definición)
```

**Parche.** Propagarlos por el estado, igual que `BUG-03`:

```diff
--- a/src/services/agent_graph/state.py
+    top_k_retrieve: int
+    top_k_rerank: int

--- a/src/api/routers/chat.py   (en ambos initial_state)
+            top_k_retrieve=request.top_k_retrieve,
+            top_k_rerank=request.top_k_rerank,

--- a/src/services/agent_graph/nodes.py
-    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=15) for q in queries]
+    retrieval_tasks = [retrieve_documents(q, tenant_id, top_k=state.get("top_k_retrieve", 15)) for q in queries]
-    best_results = await rerank_documents(state["query"], unique_candidates, top_k=10)
+    best_results = await rerank_documents(state["query"], unique_candidates, top_k=state.get("top_k_rerank", 10))
```

Alinear el default de `top_k_rerank` a 10 (o justificar 7). Si se implementa `BUG-05` opción (a), estos valores pasan a ser la base sobre la que se amplía en cada iteración.

Alternativa: eliminarlos del `ChatRequest` si no se quieren exponer, y corregir la nota de `TROUBLESHOOTING.md` §2.

**Estado: ✅ corregido (2026-09-14).** Se eligió propagarlos, como propone el parche, porque `TROUBLESHOOTING.md` §2 los presenta como la palanca con la que se resolvió un fallo real. Van por el estado hasta `researcher_node`, en ambos endpoints. Hay cuatro ajustes:

- **Un solo sitio para los valores por defecto.** `DEFAULT_TOP_K_RETRIEVE = 15` y `DEFAULT_TOP_K_RERANK = 10` viven en `requests.py`, y los importan el nodo y el router. La divergencia entre el 7 del contrato y el 10 del código era el propio defecto. Se toma 10 porque es lo que hacía la aplicación y lo que documenta `PAPER_PLAN.md`, de modo que un cliente que no envía parámetros no nota ningún cambio.
- **Límites de rango:** `top_k_retrieve` entre 1 y 50, y `top_k_rerank` entre 1 y 20. Sin ellos, al propagar, un 0 o un negativo llegaría a un `LIMIT` de Postgres, y un valor enorme multiplicaría el coste del cross-encoder, porque la búsqueda se repite por cada variante de la consulta.
- **Caché.** `semantic_cache` se indexa solo por la pregunta, así que una respuesta obtenida con otros `top_k` no es intercambiable con la de los valores por defecto. Las peticiones que los cambian no leen ni escriben caché. Sin esto, la palanca seguiría sin efecto en cuanto la pregunta estuviera cacheada.
- **Nota añadida en `TROUBLESHOOTING.md` §2.**

Verificado contra uvicorn real, con el grafo, el LLM y Postgres de verdad. `retrieve_documents` y `rerank_documents` se envolvieron solo para registrar el `top_k` que reciben y cuántos documentos devuelven. El tenant de la prueba tiene 11 documentos.

| Escenario | Antes | Después |
|---|---|---|
| Sin parámetros (control positivo) | 15 / 10 | 15 / 10 |
| `top_k_retrieve=2`, `top_k_rerank=3` | 15 / 10: ignorados | 2 candidatos por variante / 3 documentos |
| `top_k_rerank=1` | 10 documentos | 1 documento |
| `/chat/stream/` con `top_k_rerank=2` | 10 documentos | 2 documentos |
| `top_k_rerank=0`, `top_k_retrieve=-1`, `1000` | HTTP 200: descartados en silencio | HTTP 422 |
| Pregunta cacheada con `top_k_rerank=3` | Servida desde caché | Ejecuta el grafo con 3 y no escribe caché |
| Pregunta cacheada sin parámetros | Cache hit | Cache hit |
| **Comprobaciones** | **3/8** | **8/8** |

Aparte, 12 casos directos: los bordes exactos de validación (1/50/51 y 1/20/21), los valores por defecto (15, 10) y un estado de grafo sin las claves, que cae en 15/10. La base se devolvió a su estado inicial; el evaluador llegó a escribir dos filas en segundo plano, que también se purgaron.

**Evidencia colateral sobre `BUG-05`.** Con 1 a 3 documentos, el redactor pidió más información y el ciclo de auto-corrección hizo una segunda pasada del investigador **con los mismos `top_k`**: 8 búsquedas y 2 re-rankings idénticos. El reintento no amplía nada.

---

### `BUG-07` 🟡 La única suite de tests no puede ejecutarse

**Ubicación.** `tests/test_rag.py:28`

```python
vector_candidates = await retrieve_documents(query, top_k=5)
```

**Análisis.** La firma actual de `retrieve_documents` (`retriever.py:20`) es:

```python
async def retrieve_documents(query: str, tenant_id: str, top_k: int = 5) -> List[SearchResult]:
```

`tenant_id` es el segundo parámetro **posicional obligatorio**, introducido en la Fase 3 con el multi-tenancy. La llamada del test lanza `TypeError: retrieve_documents() missing 1 required positional argument: 'tenant_id'` antes de evaluar nada.

La línea 32 tiene el mismo problema en potencia: `generate_answer(query, best_results)` omite `user_profile`, aunque ahí el parámetro tiene default (`extractor.py:15`) y no rompe.

`src/pipeline.py:13` falla idénticamente.

**Impacto.** El repositorio **no tiene cobertura de tests ejecutable**. Esto contradice a `ARCHITECTURE.md` §6, que presenta esta suite como el "Sistema de Evaluación Automática" del proyecto, y al `README.md`, que lista *"Evals deterministas (DeepEval)"* como logro de la Fase 1.

`PAPER_PLAN.md` §5.2 la marca correctamente como *"Evals obsoletos de Fase 1"*, pero el archivo sigue en `tests/` sin ninguna señal en el propio código.

**Aclaración importante.** El evaluador LLM-as-a-judge de `src/services/evaluator.py` **no sustituye a estos tests**. Son mecanismos distintos y complementarios: el evaluador puntúa respuestas en producción (observabilidad), los tests verifican que el pipeline funciona antes de desplegarlo (regresión). Perder los segundos no se compensa con los primeros.

**Reproducción.**

```bash
PYTHONPATH=. uv run pytest tests/ -x
# TypeError: retrieve_documents() missing 1 required positional argument: 'tenant_id'
```

**Parche mínimo para restaurar la ejecución:**

```diff
+TEST_TENANT = "00000000-0000-0000-0000-000000000000"
+
 @pytest.mark.asyncio
 async def test_rag_contextual_relevancy_and_faithfulness():
     query = "¿Para qué sirve el archivo pyproject.toml?"
-    vector_candidates = await retrieve_documents(query, top_k=5)
+    vector_candidates = await retrieve_documents(query, TEST_TENANT, top_k=5)
     best_results = await rerank_documents(query, vector_candidates, top_k=3)
```

Requiere además `pytest-asyncio` (no declarado; ver `HYG-01`) y una base de datos poblada, por lo que es un test de integración, no unitario. La cobertura que más falta hace es unitaria y no necesita infraestructura:

- `chunk_text()` sobre un texto sintético con dos temas claramente separados → verificar que corta en el límite temático y respeta `max_tokens`.
- `route_supervisor` / `route_reviewer` sobre diccionarios de estado construidos a mano → verificar las transiciones sin tocar la red (cubriría `BUG-05` como regresión).
- `cosine_distance()` con vectores conocidos, incluido el caso de norma cero (`ingestion.py:43`).

---

### `BUG-08` 🟠 El caché del re-ranker vive en `/tmp` y su pérdida deja la app sin arrancar

**Ubicación.** `src/services/reranker.py:10`

```python
ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp/flashrank")
```

**Síntoma.** El proceso de FastAPI no arranca. La traza termina en:

```
onnxruntime.capi.onnxruntime_pybind11_state.NoSuchFile: [ONNXRuntimeError] : 3 : NO_SUCHFILE :
Load model from /tmp/flashrank/ms-marco-MiniLM-L-12-v2/flashrank-MiniLM-L-12-v2_Q.onnx failed.
File doesn't exist
```

El error apunta a un archivo cuya descarga y gestión son responsabilidad de la propia librería, lo que hace el diagnóstico poco evidente: no hay nada en el código del proyecto que mencione ese `.onnx`.

**Causa — verificada en la fuente de FlashRank.** `Ranker._prepare_model_dir` (`flashrank/Ranker.py:76-83`) decide si descargar comprobando únicamente la existencia del **directorio**, nunca la del archivo del modelo:

```python
if not self.cache_dir.exists():
    self.cache_dir.mkdir(parents=True, exist_ok=True)

if not self.model_dir.exists():
    self.logger.info(f"Downloading {model_name}...")
    self._download_model_files(model_name)
```

De ahí se sigue el modo de fallo: **si el directorio del modelo sobrevive pero su contenido desaparece, FlashRank nunca vuelve a descargar** y `ort.InferenceSession` (l. 68) falla al construirse. Como la instanciación es a nivel de módulo, el fallo ocurre en tiempo de importación y tumba el arranque completo de la API.

Es un estado **permanente**: no se recupera reintentando, reiniciando ni reinstalando dependencias. Requiere borrar el directorio a mano.

**Por qué el contenido desaparece.** `/tmp` es almacenamiento volátil por definición, y su vaciado depende del sistema (reinicio, herramientas de mantenimiento, políticas de limpieza). En la máquina auditada se observó el directorio `ms-marco-MiniLM-L-12-v2/` **vacío**, con marca de tiempo de las 00:00 del día de la auditoría; no se pudo determinar qué proceso concreto lo vació —`/etc/periodic/daily/` no existe en esta versión de macOS—, y el mecanismo exacto es irrelevante para el defecto: la garantía que el código asume (que `/tmp` persiste) no existe en ninguna plataforma.

**Confirmación de que es previo e independiente de otros cambios.** Reproducido con `git stash` sobre el árbol limpio: fallo idéntico, misma traza, con el código original.

**Comportamiento según entorno.**

| Entorno | Qué se pierde | Consecuencia |
|---|---|---|
| macOS / Linux de desarrollo | Solo los archivos; el directorio sobrevive | ❌ **App no arranca, de forma permanente** |
| Contenedor con `/tmp` en tmpfs | El árbol completo | ⚠️ Re-descarga en cada arranque: dependencia de red en el boot y cold start lento |
| CI / runner efímero | El árbol completo | ⚠️ Descarga en cada ejecución del pipeline |

Ninguna de las tres columnas es aceptable para el epic 1 del [`ROADMAP_FASE_5_ESCALABILIDAD.md`](ROADMAP_FASE_5_ESCALABILIDAD.md): una imagen que descarga su modelo de inferencia desde internet en cada arranque no es desplegable en *serverless* (Cloud Run, ECS), donde los arranques en frío son frecuentes y la salida a internet puede estar restringida.

**Atenuante.** El valor no es arbitrario: `default_cache_dir = "/tmp"` en `flashrank/Config.py:6` es el propio default de la librería. El proyecto heredó una mala convención upstream, no la inventó. Pero como pasa `cache_dir` explícitamente, cambiarlo cuesta lo mismo que dejarlo.

**Mina asociada.** En la máquina auditada queda además un directorio vacío `/tmp/flashrank/ms-marco-TinyBERT-L-2-v2/` — el modelo **por defecto** de FlashRank, el mismo que según [`PAPER.md`](PAPER.md) §9.2 devolvió 404 y forzó el cambio a `MiniLM-L-12-v2`. Por la misma lógica de existencia-de-directorio, cualquier código que instancie `Ranker()` con parámetros por defecto fallará con `NO_SUCHFILE` en lugar de intentar la descarga, reproduciendo el 404 original como un error distinto y más confuso.

**Relación con `TROUBLESHOOTING.md` §3.** Ese post-mortem documenta el síntoma *"el back está caído"* y lo atribuye a la ventana de carga de modelos con `--reload` y a procesos zombis. Este hallazgo es una **tercera causa del mismo síntoma**, cualitativamente distinta: no es una ventana de unos segundos durante el arranque, sino un estado permanente en el que el arranque no llega a completarse nunca.

**Reproducción.**

```bash
# Provocar el estado (destruye el caché del modelo):
rm -f /tmp/flashrank/ms-marco-MiniLM-L-12-v2/*
PYTHONPATH=. uv run python -c "import src.services.reranker"
# → NO_SUCHFILE, y se repetirá indefinidamente

# Comprobar el mecanismo en la fuente de la librería:
sed -n '76,83p' .venv/lib/python3.14/site-packages/flashrank/Ranker.py
grep -n "default_cache_dir" .venv/lib/python3.14/site-packages/flashrank/Config.py

# Desbloqueo manual (fuerza la re-descarga):
rm -rf /tmp/flashrank/ms-marco-MiniLM-L-12-v2
```

**Parche.** Mover el caché a una ubicación persistente y configurable:

```diff
--- a/src/services/reranker.py
+++ b/src/services/reranker.py
@@
+import os
+from pathlib import Path
+
+# /tmp es volátil y FlashRank decide si descargar mirando solo si existe el
+# DIRECTORIO del modelo: si su contenido desaparece pero el directorio queda,
+# nunca vuelve a descargar y la app deja de arrancar de forma permanente.
+RERANKER_CACHE_DIR = os.getenv(
+    "RERANKER_CACHE_DIR", str(Path.home() / ".cache" / "flashrank")
+)
+
 print("Cargando modelo local de Re-ranker (FlashRank)...")
-ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp/flashrank")
+ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir=RERANKER_CACHE_DIR)
```

Defensa complementaria, porque el directorio persistente puede corromperse igual (descarga interrumpida, disco lleno): validar que el archivo existe y no solo el directorio, y sanear antes de instanciar.

```python
from flashrank.Config import model_file_map

_model_dir = Path(RERANKER_CACHE_DIR) / "ms-marco-MiniLM-L-12-v2"
_model_file = _model_dir / model_file_map["ms-marco-MiniLM-L-12-v2"]
if _model_dir.exists() and not _model_file.exists():
    # Directorio presente sin modelo dentro: FlashRank no re-descargaría nunca.
    shutil.rmtree(_model_dir)
```

Para el epic 1 (contenerización), la solución correcta es distinta y más fuerte: **descargar el modelo en tiempo de build**, no de arranque. En el `Dockerfile`, una capa que instancie el `Ranker` una vez deja el modelo horneado en la imagen, elimina la dependencia de red en el boot y hace el cold start determinista:

```dockerfile
ENV RERANKER_CACHE_DIR=/opt/models/flashrank
RUN python -c "from flashrank import Ranker; \
    Ranker(model_name='ms-marco-MiniLM-L-12-v2', cache_dir='/opt/models/flashrank')"
```

**Estado: ✅ corregido (2026-09-11).** El caché se movió a `~/.cache/flashrank` (configurable vía `RERANKER_CACHE_DIR`) y se añadió `_ensure_model_cache()`, que sanea un directorio de modelo presente pero sin el archivo dentro. Verificado en los tres escenarios: caché sano (carga en 0,78 s sin descargar), caché corrupto (se detecta y re-descarga en vez de fallar) y override por variable de entorno. El modelo ya descargado se migró desde `/tmp` sin coste de red, y se eliminó el directorio vacío `ms-marco-TinyBERT-L-2-v2`.

---

### `BUG-09` 🟠 `/chat/stream/` no devuelve respuesta para saludos, temas fuera de alcance ni herramientas

> Hallazgo posterior a la auditoría, encontrado el 2026-09-13 al reescribir el bucle de streaming para `DOC-01`. No entra en los recuentos del §1, que son la foto del 2026-09-10.

**Ubicación.** `src/api/routers/chat.py:102-120` (código anterior a la corrección de `DOC-01`)

**Síntoma.** Un saludo por el endpoint de streaming devuelve **un solo evento SSE con la línea de progreso y nada más**:

```
eventos SSE: 1
  answer='🤖 *Supervisor evaluando estrategia...*\n\n'  confidence=None
```

La misma pregunta por `/chat/` responde correctamente. El endpoint afectado es justamente el que usa el frontend (`app.py:90` hace POST a `/chat/stream/`), así que el defecto se manifiesta en la aplicación real y no en el camino secundario.

**Causa.** El supervisor resuelve por sí mismo tres de las cuatro intenciones —`casual_greeting`, `out_of_scope` y `tool_execution`— devolviendo `final_answer` y enrutando a `END` sin pasar por el redactor (`nodes.py:28-55`, `graph.py:5-9`). El bucle del stream, en cambio, solo leía `final_answer` dentro de la rama `node_name == "generator"`:

```python
elif node_name == "generator":
    ...
    if "final_answer" in state_update and state_update["final_answer"]:
```

Cuando el grafo termina en el supervisor esa rama no se ejecuta nunca, así que la respuesta se queda en el estado y no llega al cliente. Como efecto colateral, `final_dict` sigue siendo `None` y tampoco se guarda nada en el caché semántico.

**Alcance.** Las tres herramientas (`get_current_time`, `get_crypto_price`, `get_github_profile`), los saludos y las preguntas fuera de alcance. Es decir, todo lo que no sea `knowledge_search`.

**Por qué no lo detectó la auditoría.** El §5 revisó el bucle de streaming buscando contaminación del caché (`BUG-01`) y la ruta del historial (`BUG-03`), ambos sobre el camino `knowledge_search`. Los otros tres caminos se verificaron sobre `/chat/`, donde funcionan. Es un recordatorio de que la cobertura por endpoint no equivale a cobertura por rama del grafo.

**Reproducción.**

```bash
# Con el caché purgado, para que no intercepte:
curl -N -X POST http://127.0.0.1:8000/chat/stream/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query": "Hola, qué tal", "history": []}'
# → un unico evento, solo la linea de progreso
```

**Corrección.** Sacar la lectura de `final_answer` fuera de la rama del generador, y añadir el texto al acumulado cuando el nodo que la produjo no es el redactor (el redactor ya emitió el suyo por el canal `custom`):

```python
if state_update and state_update.get("final_answer"):
    final_dict = state_update["final_answer"].model_dump()
    if node_name != "generator":
        accumulated_answer += final_dict.get("answer") or ""
    yield f"data: {json.dumps({**final_dict, 'answer': accumulated_answer})}\n\n"
```

**Estado: ✅ corregido (2026-09-13).** Corregido junto a `DOC-01`, por caer dentro del mismo bucle. Verificado: el saludo devuelve el texto del supervisor y `get_current_time` devuelve su resultado, ambos por el stream.

---

### `BUG-10` 🟠 El caché semántico ignora el historial

> Posterior a la foto: detectado el 2026-09-14 al corregir `BUG-02`. **Verificado leyendo el código; no se ha reproducido de extremo a extremo.**

**Ubicación.** `src/services/cache.py:17` (`check_semantic_cache(tenant_id, query, threshold)`) y `:46` (`save_semantic_cache(tenant_id, query, response_dict)`). Las cuatro llamadas están en `src/api/routers/chat.py:52`, `:86`, `:108` y `:175`.

**Análisis.** Desde la corrección de `BUG-03`, la respuesta depende del historial: *"¿Y en qué años?"* se resuelve contra el turno anterior, tanto en el supervisor como en el redactor. Pero el caché se consulta y se escribe solo con el texto de la pregunta. Si dos conversaciones del mismo tenant acaban en el mismo seguimiento, comparten entrada de caché: la segunda recibe la respuesta de la primera, sobre otro referente.

Las preguntas de seguimiento son cortas y genéricas, justo las que más colisionan. Si el texto es idéntico, la similitud es 1,0. Dentro de un tenant, además, un usuario puede recibir una respuesta construida a partir de la conversación de otro.

`BUG-02` y `BUG-06` restringieron qué se cachea (intención, confianza, `top_k`), pero ninguno de los dos considera el historial.

**Escenario.**
1. Conversación A: *"¿Dónde trabajó en 2024?"* → Betterfly. *"¿Y en qué años?"* → se responde sobre Betterfly y se cachea.
2. Conversación B: *"¿Qué hizo en Itaú?"* → … *"¿Y en qué años?"* → cache hit con similitud 1,0: recibe los años de Betterfly.

**Reproducción.**

```bash
grep -n "def check_semantic_cache\|def save_semantic_cache" src/services/cache.py   # no reciben historial
grep -n "semantic_cache(" src/api/routers/chat.py                                    # solo request.query
```

**Parche.** Lo mínimo es no leer ni escribir caché cuando la petición trae historial, igual que con `top_k` propios:

```python
use_cache = uses_default_retrieval(request) and not request.history
```

La alternativa conserva el caché para los seguimientos: indexarlo por las `search_queries` que el supervisor ya resolvió, que llevan el referente explícito. Obliga a consultar el caché después del supervisor, no antes, y cuesta una llamada al LLM por petición cacheada.

**Estado:** ✅ corregido el 2026-09-16 con el parche mínimo, que es el que eligió el usuario.

**Primero se reprodujo de extremo a extremo**, que era lo que le faltaba al hallazgo. Contra la API y la BD reales, como `empresa_x`, con dos referentes que existen en el corpus y el caché purgado de antemano:

| | Conversación A | Conversación B |
|---|---|---|
| Turno 1 | *"¿Qué hizo Bryan en MisterGas?"* → junio 2020 – septiembre 2022 | *"¿Qué hizo Bryan en Itaú/Kabeli?"* → mayo 2023 – marzo 2024 |
| Turno 2 (idéntico) | *"¿Y en qué años fue eso?"* → **junio 2020 a septiembre 2022** | *"¿Y en qué años fue eso?"* → **junio 2020 a septiembre 2022** |

La respuesta del turno 2 de B era **byte a byte** la de A, con un `✅ Cache Hit` en el log del servidor. El escenario del hallazgo se cumple tal como estaba descrito.

**El efecto era peor de lo que decía el análisis.** La respuesta servida desde caché empieza por *"Según el historial anterior, Bryan trabajó en MisterGas (Lipigas)…"*: no solo entrega el dato del referente equivocado, sino que se lo atribuye a un historial que no es el del usuario que la recibe. Un dato erróneo presentado con la autoridad de la propia conversación.

**Parche aplicado.** `is_cache_eligible(request)` en `src/api/routers/chat.py`, usado por los dos endpoints: `uses_default_retrieval(request) and not request.history`. Con él, el mismo guion da respuestas distintas y correctas en cada conversación (B responde *"Itaú/Kabeli … de Mayo 2023 a Marzo 2024"*), **0 aciertos de caché**, y en `semantic_cache` solo quedan las dos primeras preguntas, que son las que no llevan historial.

**Por qué no la alternativa.** Indexar por las `search_queries` del supervisor solo cierra el defecto si el supervisor incrusta siempre el referente completo; si lo resuelve a medias, la colisión vuelve. Un defecto de corrección de datos que se vuelve infrecuente es más difícil de detectar, no menos dañino. Queda como mejora posible el día que se mida el ratio de aciertos del caché, que hoy nadie mide.

**Coste asumido.** `src/frontend/app.py:87` envía el historial completo en todos los turnos salvo el primero, así que en la práctica el caché queda reservado a la primera pregunta de cada conversación — que es donde tiene valor real, porque es la que distintos usuarios repiten.

---

## 6. Rendimiento

### `PERF-01` 🟠 Sin connection pool: ~11 conexiones por consulta

**Ubicación.** No existe un solo `asyncpg.create_pool()` en el repositorio. Las nueve rutas de acceso a datos abren y cierran su propia conexión:

| Archivo:línea | Función | Patrón |
|---|---|---|
| `retriever.py:25` | `retrieve_documents` | `connect()` … `finally: close()` |
| `cache.py:21` | `check_semantic_cache` | idem |
| `cache.py:49` | `save_semantic_cache` | idem |
| `memory.py:48` | `extract_and_save_facts` | idem |
| `memory.py:70` | `retrieve_user_facts` | idem |
| `graphrag.py:51` | `insert_knowledge_graph` | idem |
| `graphrag.py:65` | `retrieve_subgraph` | idem |
| `evaluator.py:66` | `evaluate_rag_response` | idem |
| `ingestion.py:184` | `insert_documents` | idem |

El manejo con `try/finally` es correcto —no hay fugas de conexión—; el problema es la ausencia de reutilización.

**Coste por consulta.** Traza de una `knowledge_search` con Multi-Query + HyDE (el camino normal):

| Etapa | Origen | Conexiones |
|---|---|:---:|
| `check_semantic_cache` | `chat.py:77` | 1 |
| `retrieve_user_facts` | `chat.py:83` | 1 |
| `retrieve_documents` × 5 | `nodes.py:70` (query + 3 variantes + HyDE) | 5 |
| `retrieve_subgraph` | `nodes.py:86` | 1 |
| `save_semantic_cache` | `chat.py:123` | 1 |
| `extract_and_save_facts` | `chat.py:124` (background) | 1 |
| `evaluate_rag_response` | `chat.py:127` (background) | 1 |
| **Total** | | **11** |

Con el ciclo de auto-corrección de `BUG-05`: **17**.

Cada conexión implica handshake TCP, autenticación (`scram-sha-256` por defecto en PG16), negociación de parámetros de sesión y, al cerrar, terminación limpia. En local sobre loopback son unos pocos milisegundos; sobre una red real o una base gestionada (Cloud SQL, RDS) son decenas.

**Riesgo de agotamiento — el problema serio.** Las cinco recuperaciones de `nodes.py:70-71` se despachan con `asyncio.gather`, es decir, **abren cinco conexiones simultáneas**. El pico de conexiones concurrentes escala con `usuarios_concurrentes × 5`. Con el `max_connections` por defecto de PostgreSQL (100):

| Usuarios concurrentes | Pico de conexiones | Estado |
|:---:|:---:|---|
| 5 | 25 | ✅ |
| 15 | 75 | ⚠️ margen escaso |
| 20 | 100 | ❌ `FATAL: sorry, too many clients already` |

Veinte usuarios simultáneos tumban el sistema. Y el fallo no es elegante: `asyncpg.connect()` lanza, la excepción sube hasta el `except Exception` de `chat.py:65` y el usuario recibe un `500` opaco.

**Contradicción documental.** `PAPER.md` §5.5 argumenta:

> *"La complejidad temporal total de esta recuperación distribuida se reduce a $\mathcal{O}(\max_{q_i} T_{retrieval}(q_i))$ gracias al despacho paralelo de corrutinas (`asyncio.gather`), acotado por la latencia del pool de conexiones `asyncpg`."*

La cota asintótica es correcta. El pool que la sostiene no existe: hoy cada corrutina paga además el coste completo de establecer su propia conexión, que es precisamente el término que un pool elimina.

**Reproducción.**

```bash
grep -rn "create_pool" src/          # sin coincidencias
grep -rn "asyncpg.connect" src/ | wc -l   # 9
```

**Parche.** Pool global inicializado en el `lifespan` de FastAPI.

`src/api/main.py`:

```python
from contextlib import asynccontextmanager
import asyncpg, os

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        os.getenv("DATABASE_URL"), min_size=5, max_size=20, command_timeout=30,
    )
    yield
    await app.state.pool.close()

app = FastAPI(title="AI Engineer Sandbox API", ..., lifespan=lifespan)
```

Cada servicio pasa de `conn = await asyncpg.connect(DB_DSN)` + `finally: close()` a:

```python
async with pool.acquire() as conn:
    ...
```

**Importante para la corrección de `SEC-02`.** Con pool, las conexiones se **reutilizan**, y `SET app.current_tenant` es un parámetro de sesión que **persiste** en la conexión devuelta al pool. Una conexión que sirvió al tenant A conserva su `app.current_tenant` al ser adquirida por el tenant B. Si el siguiente uso no lo reestablece antes de consultar, hay fuga entre tenants.

Dos defensas, aplicar ambas:

1. Usar `SET LOCAL` dentro de una transacción explícita, para que el valor muera con ella:
   ```python
   async with pool.acquire() as conn:
       async with conn.transaction():
           await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))
           # true = local a la transacción
   ```
2. Registrar un `reset` en el pool (`asyncpg.create_pool(..., setup=...)`) que limpie el parámetro al devolver la conexión.

Este punto es la razón por la que `PERF-01` y `SEC-02` deben resolverse en el mismo cambio, no por separado.

**Estado: ✅ corregido (2026-09-15).** Hay un módulo nuevo, `src/services/db.py`, por el que pasan los nueve puntos de acceso a datos. En `src/` ya no queda ningún `asyncpg.connect` ni `SET app.current_tenant`.

- **Pool único por proceso** (`get_pool()`), de 5 a 20 conexiones, configurable con `DB_POOL_MIN_SIZE` y `DB_POOL_MAX_SIZE`. `main.py` lo precalienta en el `lifespan` (sin impedir el arranque si Postgres no está) y lo cierra al apagar.
- **`tenant_connection(tenant_id)`**: toma una conexión del pool, abre una transacción y fija el tenant como parámetro con `set_config('app.current_tenant', $1, true)`. Es también la defensa en profundidad pendiente de `SEC-02`.
- **Los embeddings se calculan antes de tomar conexión** en `retriever.py`, `cache.py` y `memory.py`. Antes se abría la conexión y luego se hacía el trabajo de CPU, con la conexión retenida sin usarse.

Ajustes respecto al parche de arriba:

- **El pool se crea bajo demanda y queda ligado al event loop**, no solo en el `lifespan`, porque también lo usan la CLI de ingesta y los scripts. La CLI lo cierra al terminar.
- **Solo hacía falta la defensa 1.** La defensa 2 ya la da asyncpg: desde 0.30 ejecuta `RESET ALL` al devolver cada conexión al pool (`Connection.get_reset_query`). Se midió con un tenant fijado a nivel de sesión, como hacía el código viejo, sobre un pool de una sola conexión. Con el reset por defecto, la petición siguiente no ve el tenant (0 filas). Con un reset vacío, **sí lo ve**: 128 tripletas ajenas. El `set_config` local a la transacción no depende de ese comportamiento.
- **Hallazgo de paso.** `ingestion.py` tenía como DSN por defecto el del superusuario `postgres`. Si faltaba `DATABASE_URL`, la ingesta eludía RLS. Con un DSN único, el valor por defecto pasa a ser `app_user`.

Verificado contra Postgres real. El código anterior son las copias exactas de HEAD (`38d6f34`) de los seis servicios, ejecutadas en el mismo proceso que los nuevos. La "ruta de lectura" son las lecturas de una `knowledge_search`: caché, memoria, las 5 búsquedas en paralelo y el grafo.

| Medida | Antes | Después |
|---|:---:|:---:|
| Conexiones nuevas por consulta (`pg_stat_database.sessions`, 10 consultas) | **8** | **0** |
| Mediana de la ruta de lectura | 206 ms | **76 ms** |
| 25 consultas concurrentes: pico de conexiones de `app_user` | 95 de 97 disponibles | **13** |
| Ídem: errores | **7 `TooManyConnectionsError`** | **0** |
| Ídem: duración total | 3,6 s | 1,7 s |

El log de Postgres registra, en el instante de la ráfaga del código viejo, decenas de `FATAL: sorry, too many clients already`.

Aislamiento, con el pool forzado a 2 conexiones para obligar a reutilizarlas entre tenants:
- 200 operaciones intercaladas de dos tenants y 60 `retrieve_subgraph` concurrentes: todas ven solo lo suyo.
- Una conexión recién devuelta al pool no conserva el tenant anterior (20 de 20).
- Con los dos tenants, caché, memoria, las 5 búsquedas y el grafo devuelven lo mismo que en HEAD.

Aplicación real (uvicorn, LLM y Postgres):
- Chat por stream (141 eventos), ingesta por API y background tasks, sin abrir **ninguna** conexión nueva en el servidor.
- Ingesta por CLI con el pool creado bajo demanda.
- Todo bajo el tenant correcto, y la base devuelta a su estado inicial.

**Límites.** La mejora de latencia es la de la ruta de base de datos en local, sobre loopback; el tiempo total de una pregunta lo siguen dominando el LLM y el re-ranking. Cerrar el pool en la CLI es higiene: sin ese cierre no apareció ningún aviso, ni con `python -X dev`, ni ningún `unexpected EOF` en el servidor.

---

### `PERF-02` 🟠 Cuatro copias del modelo de embeddings en RAM

**Ubicación.** `SentenceTransformer("all-MiniLM-L6-v2")` se instancia a nivel de módulo, de forma independiente, en cuatro archivos:

| Archivo:línea | Contexto |
|---|---|
| `src/services/retriever.py:17` | precedido de `print("Cargando modelo local de embedding...")` |
| `src/services/cache.py:14` | precedido del comentario que reconoce el problema |
| `src/services/memory.py:13` | sin comentario |
| `src/services/ingestion.py:24` | precedido de `print("Cargando modelo local...")` |

El propio código lo documenta en `cache.py:13`:

```python
# Reutilizar el mismo modelo en memoria (debería idealmente instanciarse 1 sola vez por app)
model = SentenceTransformer(EMBEDDING_MODEL)
```

**Análisis.** Al ser instanciaciones a nivel de módulo, se ejecutan en el momento del `import`. Como los cuatro módulos se importan en la cadena que arranca desde `src/api/main.py`, el proceso de FastAPI carga **cuatro instancias completas** del modelo.

`all-MiniLM-L6-v2` son ~90 MB en disco; en memoria, con los pesos en float32 más el tokenizador y el grafo de PyTorch, ronda los 90–120 MB por instancia. El sobrecoste es de unos 270–360 MB innecesarios.

**El impacto real es el arranque en frío.** Cada instanciación implica leer los pesos de disco, deserializarlos e inicializar el backend de PyTorch. Cuatro veces, secuencialmente, en el path de import.

Esto conecta directamente con un problema ya documentado. `TROUBLESHOOTING.md` §3 diagnostica:

> *"Al estar corriendo Uvicorn con la flag `--reload`, cualquier edición a archivos reiniciaba el servidor en caliente. Durante esos 10 segundos, Uvicorn carga los modelos pesados de Machine Learning (`SentenceTransformers` y `FlashRank`) a la memoria RAM. Si se hacía una petición en ese lapso exacto, se rechazaba."*

Esos "10 segundos" son en buena parte las cuatro cargas redundantes. El post-mortem trató el síntoma (matar procesos zombis, explicar la latencia al usuario) sin identificar que la carga era **cuádruple**. Consolidar reduce esa ventana a aproximadamente una cuarta parte.

**Contraste con el reranker.** `reranker.py:10` instancia `Ranker` una sola vez y todos los consumidores lo comparten por import. Es el patrón correcto, ya presente en el repositorio.

**Reproducción.**

```bash
grep -rn "SentenceTransformer(" src/
# retriever.py:17, cache.py:14, memory.py:13, ingestion.py:24
```

**Parche.** Un módulo compartido, `src/services/embeddings.py`:

```python
"""Instancia única del modelo de embeddings, compartida por todo el proceso."""
from functools import lru_cache
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384   # debe coincidir con vector(384) en sql/01_init.sql


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    print(f"Cargando modelo local de embedding {EMBEDDING_MODEL} (una sola vez)...")
    return SentenceTransformer(EMBEDDING_MODEL)


def to_pgvector(embedding) -> str:
    """Serializa un embedding al literal que espera pgvector."""
    return f"[{','.join(str(x) for x in embedding.tolist())}]"
```

Los cuatro consumidores pasan a `from src.services.embeddings import get_model, to_pgvector`.

`to_pgvector` elimina de paso otra duplicación: la expresión

```python
emb_str = f"[{','.join(str(x) for x in query_embedding.tolist())}]"
```

está repetida **siete veces** de forma literal (`retriever.py:28`, `cache.py:26`, `cache.py:54`, `memory.py:54`, `memory.py:75`, `ingestion.py:194`, y en `test_sim.py`). Centralizar `EMBEDDING_DIM` también documenta el acoplamiento con `vector(384)` del esquema, hoy implícito.

**Estado: ✅ corregido (2026-09-15).** Hay un módulo nuevo, `src/services/embeddings.py`, con la única instancia del modelo, `embed()` (el embedding en un hilo) y `to_pgvector()`. `retriever.py`, `cache.py`, `memory.py` e `ingestion.py` ya no instancian el modelo ni repiten la conversión a pgvector. Tres diferencias con el parche de arriba:

- **Se carga al importar, no en la primera llamada.** Es el mismo patrón del `Ranker`. Con `lru_cache`, la primera petición pagaría varios segundos de carga, y la caché no protege de dos hilos a la vez: varias llamadas simultáneas desde `asyncio.to_thread` podrían cargar el modelo dos veces.
- **`to_pgvector()` acepta un array de numpy o una lista**, porque `ingestion.py` guarda el embedding ya convertido a lista.
- **Al importar se comprueba que el modelo produce 384 dimensiones.** Así, un cambio de modelo falla al arrancar, con un mensaje que remite al esquema, en lugar de fallar en el primer `INSERT`.

`chunk_text` sigue llamando a `model.encode` en el hilo del event loop; eso es `PERF-03`.

Verificado importando la aplicación real (`src.api.main`) en un proceso limpio. El código anterior se ejecutó desde un worktree del commit previo (`491a71b`), con la caché de disco ya caliente para las dos variantes:

| Medida | Antes | Después |
|---|:---:|:---:|
| Instancias de `SentenceTransformer` vivas | 4 | **1** |
| Memoria nominal de parámetros | 363,6 MB (4 × 90,9) | **90,9 MB** |
| Importación de `src.api.main` | 16,6 s | **5,6 s** |
| *Physical footprint* del proceso tras importar (3 mediciones por variante) | 1350–1351 MB | **1248–1249 MB** |

Comprobaciones de equivalencia y de funcionamiento:
- **Mismos resultados** (12 entradas) que el código anterior: búsquedas de los dos tenants, caché, memoria, el troceado semántico de un texto y el hash de sus embeddings.
- **La aplicación real carga el modelo una sola vez.** Chat por stream, ingesta por API y por CLI funcionan sin errores y sin conexiones nuevas, y la base queda en su estado inicial.

**Corrección a la estimación de arriba.** El ahorro de memoria medido es de **~102 MB** de *physical footprint*, estable en las seis mediciones, y no de 270–360 MB. Las copias eran independientes: cuatro direcciones distintas de pesos, sin almacenamiento respaldado por archivo. Por qué el footprint baja menos que la memoria nominal (272 MB) queda **sin explicar**. El RSS de macOS no sirve para medirlo: osciló entre 197 y 274 MB en ejecuciones idénticas. Lo que sí se confirma es la otra mitad del análisis: el arranque en frío. Importar la API pasa de 16,6 s a 5,6 s, que es buena parte de la ventana de `TROUBLESHOOTING.md` §3.

---

### `PERF-03` 🟡 `model.encode` bloquea el event loop en la ingesta

**Ubicación.** `src/services/ingestion.py:72`, dentro de `chunk_text()`:

```python
sentence_embeddings = model.encode(sentences)
```

**Análisis.** `chunk_text` es una función **síncrona** (`def`, no `async def`, l. 48) que ejecuta inferencia de PyTorch sobre CPU. Se invoca desde dos puntos de la ruta asíncrona:

- `ingestion.py:220` — `ingest_file` para `.md` / `.txt`
- `ingestion.py:143` — `process_pdf`, una vez **por cada página** del PDF

Al no despacharse a un thread, la inferencia se ejecuta en el hilo del event loop y lo bloquea por completo.

**Contraste dentro del mismo archivo.** El repositorio usa `asyncio.to_thread` correctamente en los otros cinco puntos donde llama a `model.encode`:

| Ubicación | Patrón |
|---|---|
| `retriever.py:27` | ✅ `await asyncio.to_thread(model.encode, query)` |
| `cache.py:25` | ✅ `await asyncio.to_thread(...)` |
| `cache.py:53` | ✅ `await asyncio.to_thread(...)` |
| `memory.py:53` | ✅ `await asyncio.to_thread(...)` |
| `memory.py:74` | ✅ `await asyncio.to_thread(...)` |
| `ingestion.py:172` | ✅ `await asyncio.to_thread(model.encode, texts)` (en `generate_embeddings`) |
| **`ingestion.py:72`** | ❌ **llamada directa** |

Es la única excepción — un descuido, no una decisión.

**Impacto.** Durante la ingesta de un PDF de 20 páginas con ~40 oraciones por página, `model.encode` se invoca 20 veces sobre lotes de 40 oraciones. En cada una, el servidor **deja de responder a todas las peticiones**: chats en curso, streams SSE abiertos y el propio `/health`. Un balanceador con healthchecks agresivos podría marcar la instancia como caída durante una ingesta grande.

Nótese que `generate_embeddings` (l. 168-175) sí despacha correctamente — el bloqueo ocurre antes, en la fase de chunking.

**Reproducción.**

```bash
grep -n "model.encode" src/services/ingestion.py
# 72:    sentence_embeddings = model.encode(sentences)      ← sin to_thread
# 172:   embeddings_np = await asyncio.to_thread(model.encode, texts)
```

**Parche.** Despachar la función completa, que es la unidad de trabajo CPU-bound:

```diff
--- a/src/services/ingestion.py
@@ async def process_pdf(file_path: str) -> List[DocumentChunk]:
         if text.strip():
-            page_chunks = chunk_text(text, source_type=f"pdf_page_{page_num+1}")
+            page_chunks = await asyncio.to_thread(chunk_text, text, f"pdf_page_{page_num+1}")
             chunks.extend(page_chunks)
@@ async def ingest_file(file_path: str, tenant_id: str) -> IngestionResult:
-        chunks = chunk_text(content, source_type="markdown")
+        chunks = await asyncio.to_thread(chunk_text, content, "markdown")
```

**Nota relacionada, misma causa.** Las tres herramientas de `src/services/tools.py` usan `requests` (síncrono) y se invocan desde `supervisor_node`, que es `async` (`nodes.py:40`: `tool_result = tool_func(**intent.tool_args)`). Cada llamada a CoinGecko o GitHub bloquea el event loop hasta el timeout de 5 segundos. La corrección es la misma —`await asyncio.to_thread(tool_func, **intent.tool_args)`— o migrar `tools.py` a `httpx.AsyncClient`, que ya está en el árbol de dependencias como transitiva de `anthropic`.

**Estado: ✅ corregido (2026-09-15).** Tres cambios:

- **`chunk_text` se despacha completo con `asyncio.to_thread`** en sus dos llamadas: `ingest_file` (texto y markdown) y `process_pdf` (cada página).
- **Las herramientas del supervisor también**, con `await asyncio.to_thread(tool_func, **intent.tool_args)`. Se descartó migrar `tools.py` a `httpx.AsyncClient` porque cambiaría la interfaz de las herramientas por lo mismo que resuelve una línea. Contrapartida: una herramienta lenta ocupa un hilo del ejecutor por defecto, que comparte con los embeddings, hasta su timeout de 5 s.
- **Se corrige el comentario de `chunk_text`** que afirmaba que el embedding *"es instantáneo localmente"*: tardó entre 0,6 y 1,2 s con 400 oraciones.

Verificado contra el servidor real. Durante cada escenario, un cliente sondea `/health` cada 20 ms, y lo que se mide es cuánto espera como máximo. En la ingesta se sustituyeron solo la inserción en BD y la extracción de GraphRAG, que no intervienen en el bloqueo; el troceado y los embeddings son los reales. Las herramientas se envolvieron solo para registrar su duración.

| Escenario | Trabajo síncrono | `/health` máx. antes | `/health` máx. después |
|---|---|:---:|:---:|
| Reposo | — | 17,6 ms | 13,2 ms |
| Ingesta de un `.txt` de 400 oraciones (58 fragmentos) | `chunk_text`: 1151 ms / 604 ms | **1182 ms** | **21 ms** |
| Chat con `get_crypto_price` (CoinGecko real) | herramienta: 178 ms / 129 ms | **204 ms** | **13,6 ms** |

Antes, la espera de `/health` coincidía con la duración del trabajo síncrono: el servidor no atendía nada más. Salen los mismos 58 fragmentos, la herramienta devuelve el precio y la base queda en su estado inicial. La diferencia de duración de `chunk_text` entre ejecuciones no se debe al cambio: el hilo no acelera el cálculo, solo evita que congele el servidor.

**Ruta de PDF**, medida aparte, sin BD ni LLM, con un latido de 5 ms en el mismo proceso: un PDF de 20 páginas con 80 oraciones cada una, procesado por la versión anterior (`e711924`) y por la nueva.

| | Antes | Después |
|---|:---:|:---:|
| Parada máxima del event loop | **1060 ms** | **16 ms** |
| Duración de `process_pdf` | 1,05 s | 1,00 s |
| Fragmentos | 217 | 217, idénticos |

**Precisión al análisis de arriba.** Con un PDF solo de texto no hay un bloqueo por página, sino **uno solo que dura todo el procesado**: 1060 ms de parada en 1,05 s. `process_pdf` no tiene ningún `await` entre páginas cuando no hay imágenes, así que no devolvía el control al event loop hasta terminar. Siguen siendo síncronos, y quedan como están, `fitz.open`/`get_text` y las lecturas de archivo de `ingest_file`, que en esta medición son de milisegundos.

---

### `PERF-04` 🟡 `max_tokens=300` trunca al evaluador

**Ubicación.** `src/services/evaluator.py:58-63`

```python
evaluation = await client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=300,
    messages=[{"role": "user", "content": prompt}],
    response_model=RAGEvaluation,
)
```

**Análisis.** El presupuesto de 300 tokens debe cubrir la envoltura de tool-calling que genera Instructor, tres floats, y el campo `reasoning`, que es texto libre sin límite declarado:

```python
reasoning: str = Field(..., description="Breve explicación de las puntuaciones otorgadas.")
```

"Breve" es una instrucción en lenguaje natural, no una restricción. Nada impide al modelo escribir un párrafo de 400 tokens justificando las tres métricas.

**Modo de fallo.** Cuando la generación alcanza `max_tokens`, la respuesta se corta a mitad del JSON. Instructor no puede parsearlo, lanza excepción, y el `except Exception` de la línea 86 la absorbe:

```python
except Exception as e:
    print(f"⚠️ [Evaluator] Error durante la evaluación: {e}")
```

La evaluación se pierde. No queda fila en `rag_evaluations`, no hay métrica, no hay alerta. Solo una línea en stdout que nadie está leyendo en producción.

**Patrón ya diagnosticado.** `TROUBLESHOOTING.md` §6 documenta exactamente este fallo en el extractor:

> *"Se aumentó `max_tokens` de 1024 a 2048 para que no se corte por el límite y rompa la validación del JSON final."*

El extractor está hoy en 8192 (`extractor.py:43` y `:78`). El evaluador quedó en 300 y no recibió el mismo tratamiento.

**Sesgo estadístico resultante.** El truncamiento no es aleatorio: afecta con más probabilidad a las evaluaciones cuyo razonamiento es más largo, que son típicamente las de casos problemáticos (respuestas con alucinaciones parciales, contexto ambiguo). Es decir, **las evaluaciones que más importan son las que más se pierden**, y las métricas agregadas quedan sesgadas al alza. Esto compromete directamente el epic 2 del `ROADMAP_FASE_5_ESCALABILIDAD.md` (dashboard de evaluaciones): las series temporales se construirían sobre una muestra sesgada.

**Reproducción.**

```bash
grep -n "max_tokens" src/services/*.py
# evaluator.py:60  → 300      ← el más bajo con campo de texto libre
# memory.py:38     → 200      (solo lista de strings cortos; aceptable)
# router.py:76     → 500
# graphrag.py:37   → 1024
# ingestion.py:119 → 1000
# extractor.py:43  → 8192
# extractor.py:78  → 8192
```

**Parche.** Ampliar el presupuesto y acotar el campo en el esquema:

```diff
--- a/src/services/evaluator.py
     reasoning: str = Field(
         ...,
-        description="Breve explicación de las puntuaciones otorgadas."
+        description="Explicación concisa de las puntuaciones, máximo 3 frases.",
+        max_length=600,
     )
@@
-        max_tokens=300,
+        max_tokens=1024,
```

Combinar con el parche de `DOC-02` (añadir `ge`/`le` a los tres scores), que corrige el otro modo de fallo silencioso del mismo módulo.

**Recomendación transversal.** Tres subsistemas absorben excepciones sin dejar rastro estructurado: `evaluator.py:86`, `memory.py:63` y `graphrag.py:42`. Los tres son background o best-effort, así que no deben propagar — pero deberían registrar con el módulo `logging` y una métrica de contador, no con `print`. Hoy, si el evaluador dejara de funcionar por completo, nada lo indicaría salvo la ausencia de filas nuevas en una tabla que nadie consulta.

**Observación medida (2026-09-14).** Arrancando el servidor con stdout sin búfer, se vio el error que el `print` de la línea 86 hacía invisible: *"The output is incomplete due to a max_tokens length limit"*. El diagnóstico queda confirmado, pero el fallo es **intermitente**, no sistemático. Depende de lo larga que salga la respuesta del juez, no del tamaño del corpus:

| Verificación | Contexto del juez | Resultado |
|---|---|---|
| `BUG-02` | 10 documentos del corpus real | Falló por `max_tokens` |
| `BUG-04` | 1 documento (base nueva) | Guardó la evaluación |
| `BUG-06`, `BUG-05` | Hasta 10 documentos del corpus real | Guardó evaluaciones en varias ejecuciones |

La base de desarrollo no tiene ninguna evaluación. El mensaje del commit `d198be1` (`BUG-02`) afirma que el evaluador falla siempre; es incorrecto. Para las pruebas, conviene contar con que puede aparecer una fila en `rag_evaluations` después de responder.

**Estado: ✅ corregido (2026-09-15)**, junto con `DOC-02`, como recomienda el parche. Cambios en `evaluator.py`:

- `max_tokens` pasa de 300 a 1024.
- `reasoning` queda acotado con `max_length=600` y una descripción que pide como máximo tres frases.
- `max_retries=3` explícito. Instructor 1.16 ya hacía 3 intentos por defecto en `AsyncInstructor.create`, que es lo que devuelve `from_anthropic`; se fija para no depender de lo que traiga otra versión.

Verificado con el juez real (Claude Haiku). Se tomaron 5 preguntas del corpus, con 10 documentos de contexto recuperados y re-rankeados y la respuesta real del redactor, generados una vez y compartidos. Cada pregunta se evaluó 3 veces con el evaluador anterior (`e711924`) y 3 con el nuevo, alternando:

| | Antes | Después |
|---|:---:|:---:|
| Evaluaciones guardadas | 5/15 | **15/15** |
| Perdidas por truncado (`max_tokens`) | **10/15** | 0 |
| `reasoning` guardado (mediana / máximo) | 746 / 785 caracteres | 438 / 564 caracteres |

Todas las puntuaciones nuevas están en [0, 1], y la base se devolvió a su estado inicial.

**Precisión a la observación de arriba.** Con un contexto realista de 10 documentos, la pérdida no era ocasional: afectaba a **dos de cada tres** evaluaciones. Las pocas que se guardaban llevaban razonamientos de hasta 785 caracteres, al borde de lo que cabía en 300 tokens junto al JSON.

Queda sin aplicar la recomendación transversal: registrar con `logging` en lugar de `print` en `evaluator.py`, `memory.py` y `graphrag.py`.

---

## 7. Divergencias entre Documentación y Código

Esta es la categoría más relevante para un repositorio de portafolio: son afirmaciones **verificables** por cualquiera que abra el código junto al paper.

### `DOC-01` 🟠 El streaming token-a-token ya no existe

**Lo que dice la documentación.**

`README.md` §3, como característica SOTA destacada:

> *"Streaming SSE + Pydantic v2: Generación estructurada de respuestas parciales en tiempo real a través de Server-Sent Events usando la librería `Instructor`. Garantiza JSON determinista sin alucinaciones de sintaxis."*

`TROUBLESHOOTING.md` dedica **dos post-mortems completos** al tema: §4 (*"El Frontend de Streamlit se congela al hacer Streaming (SSE)"*, con el análisis del backpressure y la solución vía `st.write_stream()`) y §5 (*"Error de Tipos por Objetos Parciales"*, sobre `instructor.Partial` emitiendo `{"answer": null}`).

`PAPER.md` §4.4 lo formaliza en la capa de presentación.

**Lo que hace el código.**

`generate_answer_stream()` (`src/services/extractor.py:56-90`) implementa el streaming real —`Partial[StructuredAnswer]`, `stream=True`, emisión incremental por token:

```python
response = await client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=8192,
    messages=[{"role": "user", "content": prompt}],
    response_model=Partial[StructuredAnswer],
    stream=True
)
async for partial_model in response:
    yield partial_model.model_dump_json() + "\n"
```

y **no se invoca desde ningún punto del repositorio**. Quedó huérfana en la migración a LangGraph: `generator_node` (`nodes.py:107`) llama a `generate_answer` —la versión no-streaming.

Lo que emite hoy `/chat/stream/` (`chat.py:102-120`) son **cuatro eventos SSE discretos**:

| # | Momento | Contenido |
|:---:|---|---|
| 1 | tras `supervisor` | `"🤖 *Supervisor evaluando estrategia...*"` |
| 2 | tras `researcher` | `+ "🔍 *Investigador buscando en Postgres Vector y GraphRAG...*"` |
| 3 | al entrar `generator` | `+ "✍️ *Redactor estructurando respuesta final...*"` |
| 4 | tras `generator` | `+ ` **la respuesta completa de golpe** |

**Impacto.** Es *progress streaming*, no *token streaming*. El efecto visual de escritura en vivo —el "auténtico efecto ChatGPT" que describe `TROUBLESHOOTING.md` §4— se perdió: el usuario ve tres líneas de estado aparecer rápido y luego un bloque de texto completo de golpe, tras varios segundos de espera.

El frontend sigue preparado para lo anterior: `stream_parser()` (`app.py:100-124`) calcula diffs de caracteres entre eventos consecutivos, lógica diseñada para cientos de eventos incrementales que ahora recibe cuatro. Funciona, pero no aporta nada.

**Nota sobre `astream`.** El código usa `agent_graph.astream(initial_state)` (`chat.py:102`), que emite **una actualización por nodo completado** — no por token. Para streaming real de tokens a través de LangGraph hace falta `astream_events(..., version="v2")` y filtrar los eventos `on_chat_model_stream`. La elección de `astream` es coherente con lo que el código hace; simplemente no es lo que la documentación describe.

**Reproducción.**

```bash
grep -rn "generate_answer_stream" src/
# única coincidencia: src/services/extractor.py:56 (la definición)

grep -n "astream\|astream_events" src/api/routers/chat.py
# 102: async for output in agent_graph.astream(initial_state):
```

**Corrección.** Dos caminos, y hay que elegir explícitamente:

**(a) Recuperar la característica.** Migrar a `astream_events` y propagar los tokens del generador:

```python
async for event in agent_graph.astream_events(initial_state, version="v2"):
    kind = event["event"]
    if kind == "on_chain_start" and event["name"] in ("supervisor", "researcher"):
        yield f"data: {json.dumps({'answer': progreso, 'sources': []})}\n\n"
    elif kind == "on_chat_model_stream":
        # fragmento incremental del generador
        ...
```

Requiere que `generator_node` invoque `generate_answer_stream` y que LangGraph propague el generador asíncrono — trabajo real, no trivial.

**(b) Alinear la documentación con la realidad.** Borrar `generate_answer_stream` (código muerto), reescribir la característica del README como *"Streaming de progreso por nodo vía SSE"* —que es honesto y sigue siendo una buena característica— y añadir una nota en `TROUBLESHOOTING.md` §4-5 indicando que describen la implementación de la Fase 3, sustituida en la Fase 4.

Cualquiera de las dos es aceptable. Lo que no lo es es el estado actual: una característica anunciada con función muerta en el árbol.

**Estado: ✅ corregido (2026-09-13) por la vía (a).** Se recuperó el streaming token-a-token.

**Corrección al camino propuesto.** El boceto de (a) no habría funcionado: `astream_events` emite `on_chat_model_stream` solo para *chat models* de LangChain, y este proyecto llama al SDK de Anthropic directamente a través de `instructor`. Por ese camino no habría llegado ni un token. El mecanismo correcto para esta arquitectura es el canal `custom` del grafo: `generator_node` obtiene un `get_stream_writer()` y escribe los fragmentos según los recibe; `/chat/stream/` consume `astream(stream_mode=["updates", "custom"])`, que entrega tuplas `(modo, chunk)` con los `custom` intercalados antes del `updates` del nodo. Fuera de un contexto de streaming —el `ainvoke` de `/chat/`— el writer es un no-op, así que el endpoint no-streaming no se entera.

`generate_answer_stream` deja de ser código muerto y cambia de contrato: emite el modelo parcial en lugar de su JSON serializado, porque el nodo necesita el texto incremental para el SSE y el objeto final para el estado. Además, ambos redactores pasan a compartir `_build_prompt()`: tener dos copias del prompt fue justamente la causa de que la instrucción anti-texto-plano de [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) §6 viviera solo en la versión muerta (ver Anexo D).

**Medido contra un servidor real** —no con `TestClient`, que bufferiza la respuesta entera y da tiempos idénticos para todos los eventos—, misma pregunta:

| | Eventos SSE | 1er texto del redactor | Respuesta completa |
|---|:---:|:---:|:---:|
| Antes | 4 | 13,49 s (el bloque entero de golpe) | 13,91 s |
| Después | 244 | 9,55 s | 12,51 s |

El texto empieza unos 4 segundos antes y los últimos ~3 segundos son escritura en vivo. Conviene no exagerar la mejora: el grueso de la latencia no está en la generación sino en recuperación y re-ranking, así que el usuario sigue esperando unos 9 segundos antes de ver la primera letra. Reducir esa parte es asunto de `PERF-01` y `PERF-02`.

**Dos detalles que hubo que resolver.** El ciclo de auto-corrección (`BUG-05`) puede pasar por el redactor dos veces, y `stream_parser()` (`app.py:118`) solo renderiza cuando el texto crece: un segundo borrador que encogiera la cadena desincronizaría la UI. Por eso el reintento se anuncia y se encadena en lugar de reemplazar. Y como en `Partial` todos los campos son opcionales, un parcial que nunca cierre el esquema —generación truncada por `max_tokens`, corte a media respuesta— no se rellena a mano: se repliega a `generate_answer` y se encadena su respuesta.

El frontend no se tocó: `stream_parser()` se escribió para esto y hasta ahora recibía cuatro eventos donde esperaba cientos. Verificado además que lo persistido en caché y lo enviado al evaluador siguen limpios de los mensajes de progreso (`BUG-01`), que el saludo, las herramientas y el endpoint no-streaming siguen bien, y que la resolución de correferencias (`BUG-03`) sigue funcionando sobre el camino de streaming.

---

### `DOC-02` 🟠 El paper afirma validaciones Pydantic que no existen

**Lo que dice la documentación.** `PAPER.md` §5.6 (y `PAPER_EN.md` §5.6):

> *"Las restricciones Pydantic `ge=0.0` y `le=1.0` rechazan forzosamente cualquier respuesta del LLM fuera del soporte probabilístico, arrojando una `ValidationError` que garantiza la estabilidad del sistema métrico de auditoría."*

**Lo que hace el código.** `RAGEvaluation` (`src/services/evaluator.py:14-30`) declara los tres scores **sin ninguna restricción de rango**:

```python
class RAGEvaluation(BaseModel):
    faithfulness_score: float = Field(
        ...,
        description="Puntuación de 0.0 a 1.0 indicando si la respuesta es fiel al contexto (sin alucinaciones)."
    )
    relevance_score: float = Field(...)          # sin ge/le
    context_precision_score: float = Field(...)  # sin ge/le
```

El rango es una **descripción en lenguaje natural**, no una restricción. Pydantic acepta `1.7`, `-0.3` o `42.0` sin objeción.

**De dónde viene la confusión.** `StructuredAnswer.confidence_score` (`src/models/structured.py:11`) **sí** las tiene:

```python
confidence_score: float = Field(..., description="Nivel de confianza...", ge=0.0, le=1.0)
```

El paper describe correctamente el patrón del proyecto, pero lo atribuye al módulo equivocado.

**Cadena de fallo real.** La única defensa efectiva está en SQL (`sql/01_init.sql:64-66`):

```sql
faithfulness_score FLOAT CHECK (faithfulness_score >= 0.0 AND faithfulness_score <= 1.0),
```

Si el juez devuelve `1.2`:

1. Pydantic valida → ✅ pasa.
2. `INSERT` viola el `CHECK` → `asyncpg.exceptions.CheckViolationError`.
3. El `except Exception` de `evaluator.py:86` la absorbe con un `print`.
4. **La evaluación se pierde en silencio.**

Es exactamente el fallo que el paper afirma que está prevenido. Y es la segunda vía de pérdida silenciosa del mismo módulo, junto a `PERF-04`.

**Por qué es probable.** Los LLMs devuelven valores fuera de rango en tareas de puntuación con más frecuencia de la esperada, especialmente con temperatura por defecto (1.0, según `PAPER_PLAN.md` §3.4): confunden escalas 0–1 con 0–10, o redondean a `1.0000001`.

**Reproducción.**

```bash
grep -n "ge=\|le=" src/services/evaluator.py    # sin coincidencias
grep -n "ge=\|le=" src/models/structured.py     # 11: ge=0.0, le=1.0
```

**Parche.** Alinea el código con lo que el paper ya afirma —no hace falta tocar el paper:

```diff
--- a/src/services/evaluator.py
 class RAGEvaluation(BaseModel):
     faithfulness_score: float = Field(
-        ...,
+        ..., ge=0.0, le=1.0,
         description="Puntuación de 0.0 a 1.0 indicando si la respuesta es fiel al contexto (sin alucinaciones)."
     )
     relevance_score: float = Field(
-        ...,
+        ..., ge=0.0, le=1.0,
         description="Puntuación de 0.0 a 1.0 indicando si la respuesta responde directamente a la pregunta."
     )
     context_precision_score: float = Field(
-        ...,
+        ..., ge=0.0, le=1.0,
         description="Puntuación de 0.0 a 1.0 indicando si el contexto provisto contenía la información necesaria o si había basura irrelevante."
     )
```

Con esto, Instructor detecta la `ValidationError` y **reintenta inyectando el error al modelo** —el comportamiento de auto-corrección que `ARCHITECTURE.md` §4 describe para el extractor— en lugar de perder el registro. El `CHECK` de SQL pasa a ser la segunda línea de defensa que debía ser.

**Estado: ✅ corregido (2026-09-15)**, en el mismo cambio que `PERF-04`. Las tres puntuaciones de `RAGEvaluation` llevan `ge=0.0, le=1.0`. El código hace ahora lo que afirma `PAPER.md` §5.6, así que el paper no necesita cambios.

Verificado sin LLM, con `faithfulness_score=1.2`:
- **Antes:** el esquema lo acepta, y el `INSERT` real en `rag_evaluations` falla por el `CHECK`. Es la ruta de pérdida silenciosa descrita arriba.
- **Después:** el esquema lo rechaza con `ValidationError` antes de llegar a SQL, donde Instructor puede reintentar.

En las 15 evaluaciones reales de la verificación de `PERF-04` no apareció ninguna puntuación fuera de rango, así que el reintento por rango no llegó a observarse en la práctica.

---

### `DOC-03` 🟠 `.env.example` no permite arrancar el proyecto

**Lo que dice la documentación.** `README.md` §"Cómo Ejecutar", paso 3:

> *"Configurar las Credenciales: Copia el archivo `.env.example` a `.env` y añade tu `ANTHROPIC_API_KEY`."*

`PAPER_PLAN.md` §1 lo describe como: *"Plantilla de variables de entorno (API keys de Anthropic y JWT secret)"*.

**Lo que contiene el archivo.**

```bash
# Base de datos
DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5433/postgres

# OpenAI
OPENAI_API_KEY=tu_clave_de_openai_aqui

# Langfuse
LANGFUSE_SECRET_KEY=tu_secret_key_de_langfuse
LANGFUSE_PUBLIC_KEY=tu_public_key_de_langfuse
LANGFUSE_HOST=https://cloud.langfuse.com
```

**Tres problemas.**

1. **No hay `ANTHROPIC_API_KEY`.** El README dice "añade tu `ANTHROPIC_API_KEY`", pero la plantilla no tiene la entrada. Las siete llamadas al LLM leen `os.getenv("ANTHROPIC_API_KEY")` y recibirían `None`.

2. **Hay `OPENAI_API_KEY`, que no se usa en ningún sitio.** Es un residuo de la Fase 1. Su origen está en `CONTEXT.md`, que sigue describiendo el stack completo con OpenAI:
   > *"Clientes & Modelos: OpenAI (`gpt-4o-mini`, `text-embedding-3-small`), `Instructor`."*
   
   Ese documento también congela el "Estado Actual" en la Fase 1 (solo `extractor.py`, `retriever.py`, `reranker.py`) y no menciona Anthropic, LangGraph, GraphRAG, memoria ni evaluador.

3. **No hay `JWT_SECRET_KEY`** — porque no existe (`SEC-01`). `PAPER_PLAN.md` afirma que la plantilla la incluye; no es cierto.

**Cuarto problema, el más grave: el DSN de ejemplo desactiva RLS.**

La plantilla apunta a `postgresql://postgres:...` — el **superusuario propietario** de las tablas. Pero `sql/create_app_user.sql` existe precisamente para crear un rol distinto:

```sql
CREATE USER app_user WITH PASSWORD 'apppassword';
```

La razón es que en PostgreSQL **el propietario de una tabla elude sus propias políticas RLS** salvo que se declare `FORCE ROW LEVEL SECURITY`. Y `01_init.sql` no declara `FORCE` en ninguna de sus cuatro tablas (`BUG-04`).

Consecuencia: quien siga el README literalmente arranca el sistema con el aislamiento multi-tenant **desactivado de facto** sobre `documents`, `semantic_cache`, `user_memory` y `rag_evaluations` — mientras el README, el paper y `GRAPHRAG_ARCHITECTURE.md` afirman que está activo. Todas las consultas verían todas las filas de todos los tenants.

Los defaults del código sí apuntan al usuario correcto (`retriever.py:13`, `cache.py:10`, `memory.py:11`, `graphrag.py:11`, `evaluator.py:10` usan `app_user`), con una excepción: `ingestion.py:21` cae por defecto a `postgres`. Inconsistencia menor pero en el mismo sentido.

**Reproducción.**

```bash
cat .env.example
grep -rn "ANTHROPIC_API_KEY" .env.example        # sin coincidencias
grep -rn "OPENAI" src/                            # sin coincidencias
grep -rn 'DB_DSN = os.getenv' src/services/ | grep -c app_user   # 5 de 6
```

**Parche.** Reescribir `.env.example`:

```bash
# --- Base de datos ---
# IMPORTANTE: usar app_user, no postgres. El propietario de las tablas elude
# las políticas RLS salvo FORCE ROW LEVEL SECURITY (ver sql/create_app_user.sql).
DATABASE_URL=postgresql://app_user:apppassword@localhost:5433/postgres

# --- Anthropic (Claude) ---
ANTHROPIC_API_KEY=sk-ant-...

# --- Autenticación ---
# Generar con: openssl rand -hex 32
JWT_SECRET_KEY=cambia_esto_por_una_clave_aleatoria

# --- Observabilidad (opcional) ---
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

Alinear `ingestion.py:21` al mismo default, y añadir a `CONTEXT.md` un encabezado de documento histórico (o reescribirlo con el stack real).

**Estado:** ✅ corregido el 2026-09-16.

**Qué seguía abierto.** Parte del hallazgo se había resuelto por el camino: `JWT_SECRET_KEY` entró en la plantilla con `SEC-01`, `FORCE ROW LEVEL SECURITY` con `BUG-04` y el valor por defecto de `ingestion.py` con `PERF-01`. Seguían abiertos la falta de `ANTHROPIC_API_KEY`, el `OPENAI_API_KEY` sin uso y el DSN de superusuario. Y había un problema nuevo, **introducido por `SEC-05`**: el README ordenaba `docker compose up -d` (paso 2) antes de crear `.env` (paso 3), pero desde `SEC-05` Compose exige `TENANT_SIGNING_KEY` para interpolar el servicio.

**Verificación: arranque desde un clon limpio** de `HEAD`, siguiendo solo las instrucciones, en un proyecto Compose aparte. Desviaciones declaradas: se reutilizó la `.venv` del repositorio en lugar de `uv sync` (las dependencias son `HYG-01`), y se usaron otros puertos porque los de desarrollo estaban ocupados; `DATABASE_URL` se cambió solo en el puerto.

| Paso | Archivos anteriores | Archivos corregidos |
|---|---|---|
| Levantar la base | Falla: `required variable TENANT_SIGNING_KEY is missing a value`, antes y después de copiar `.env` | Arranca (el README pide rellenar `.env` antes) |
| `ANTHROPIC_API_KEY` en la plantilla | No existe; hay que añadir la línea a mano | Presente, marcada como obligatoria |
| Arrancar la API con lo que pide el README | Falla: `RuntimeError: JWT_SECRET_KEY no está configurada` | Arranca |
| Rol con el que conecta la API | `postgres` (superusuario) | `app_user` |

**Aislamiento, de extremo a extremo.** En cada brazo, `bryan` (tenant 0000) ingirió por la API un documento con un dato imposible de adivinar (una ciudad inventada), y `empresa_x` (tenant 1111) preguntó por él. `top_k_rerank=9`, para que ninguna petición tocara el caché.

| | Archivos anteriores | Archivos corregidos |
|---|---|---|
| `empresa_x` (otro tenant) | **Recibe el dato**, con 2 fuentes | No lo recibe: 0 fuentes, contexto vacío |
| `bryan` (control positivo) | Lo recibe | Lo recibe |
| Filas de `documents` que ve la conexión de `empresa_x` | 1, de otro tenant | 0 |

Con la plantilla anterior, un tenant leía de extremo a extremo los documentos de otro, pese a `FORCE`, a la firma de `SEC-05` y a todo lo demás: un superusuario no pasa por las políticas. El control positivo descarta que el resultado de la plantilla corregida sea un fallo de la recuperación.

Un primer intento preguntaba por un "código de acceso". El supervisor se negó a buscarlo por parecerle una credencial (0 fuentes y *"No puedo proporcionar códigos de acceso…"*), así que ese resultado no decía nada sobre el aislamiento y se repitió con un dato inocuo.

**Cambios.** `.env.example` reescrito: `app_user` en `DATABASE_URL`, con la razón; `ANTHROPIC_API_KEY` obligatoria; sin `OPENAI_API_KEY`; y Langfuse vacío y opcional (comprobado: la aplicación funciona igual sin sus claves). En el README, rellenar `.env` pasa a ser el paso 2, antes de levantar la base, con los comandos para generar las dos claves. `CONTEXT.md` lleva un encabezado de documento histórico.

**Fuera de alcance.** `scratch_db.py` y `test_db.py`, en la raíz, siguen conectando como `postgres`. Son el código muerto de `HYG-02`: no los usa la aplicación ni los cita la documentación.

---

### `DOC-04` 🟡 `NetworkX` documentado pero nunca usado

**Lo que dice el `README.md` §2:**

> *"GraphRAG (Grafos de Conocimiento): Extracción dinámica de entidades y relaciones (**NetworkX**) guardadas en Postgres."*

**Lo que hace el código.** `src/services/graphrag.py` (99 líneas) es exclusivamente:
- una llamada a Claude vía Instructor para extraer tripletas (`extract_knowledge_graph`),
- dos consultas SQL (`insert_knowledge_graph`, `retrieve_subgraph`).

No hay ninguna estructura de grafo en memoria, ningún algoritmo topológico, ninguna importación de `networkx` en todo el repositorio. El paquete no está declarado en `pyproject.toml`; existe en el entorno solo como dependencia transitiva.

**Contraste con el roadmap.** `ROADMAP_FASE_5_ESCALABILIDAD.md` §5 lo plantea **correctamente como trabajo futuro**:

> *"Implementar la librería `NetworkX` o migrar los datos a un motor nativo de grafos como Neo4j / Apache Age. Computar algoritmos de PageRank, detección de comunidades (Leiden) o Betweenness Centrality."*

El roadmap es honesto; el README presenta como implementado lo que el roadmap describe como pendiente.

`PAPER.md` §5.5 también es honesto: describe el motor como *"ingenuo"* con *"interpolación relacional plana de 1-hop"*.

**Reproducción.**

```bash
grep -rn "networkx\|import nx" src/ tests/     # sin coincidencias
grep -n "networkx" pyproject.toml              # sin coincidencias
```

**Parche.** En `README.md`, eliminar la atribución falsa:

```diff
-*   **GraphRAG (Grafos de Conocimiento):** Extracción dinámica de entidades y relaciones (NetworkX) guardadas en Postgres. Al consultar, se recuperan sub-grafos para entender el panorama general.
+*   **GraphRAG (Grafos de Conocimiento):** Extracción de tripletas (entidad–relación–entidad) mediante LLM, persistidas en PostgreSQL bajo RLS. Al consultar, se recupera un sub-grafo de 1 salto que se inyecta en el contexto sin pasar por el re-ranker. (Análisis topológico —PageRank, centralidad— planificado en [Fase 5](docs/ROADMAP_FASE_5_ESCALABILIDAD.md).)
```

---

### `DOC-05` 🟡 `ARCHITECTURE.md` congelado en la Fase 1

**Análisis.** El documento describe una arquitectura que ya no existe, **sin ninguna nota de que sea histórico**. Su nombre —`ARCHITECTURE.md`, en la raíz— invita a leerlo como referencia primaria.

| `ARCHITECTURE.md` afirma | Ubicación | Estado real | Ubicación real |
|---|---|---|---|
| Chunking fijo de 256 tokens, overlap 30, `tiktoken` | §2 | Semantic chunking estadístico, `max_tokens=400`, sin overlap | `ingestion.py:48-108` |
| Retriever puramente vectorial, Top-K coseno | §3, diagrama | Búsqueda híbrida Vector + FTS fusionada con RRF (`k=60`) | `retriever.py:34-58` |
| Reranker `ms-marco-TinyBERT-L-2-v2` | §3 | `ms-marco-MiniLM-L-12-v2` | `reranker.py:10` |
| Pipeline lineal Ingestión → Retrieval → Generación | diagrama | `StateGraph` cíclico de 3 nodos con ciclo de revisión | `graph.py:20-51` |
| Evals con DeepEval en `tests/test_rag.py` | §6 | Suite rota e inejecutable | `BUG-07` |
| Sin mención de multi-tenancy, RLS, GraphRAG, memoria, caché ni evaluador | — | Los cinco implementados | Fases 3-4 |

El diagrama Mermaid de la cabecera describe el pipeline lineal de la Fase 1 completo, incluidas las etiquetas *"Fase 1: Ingestión"*, *"Fase 2: Recuperación"*, *"Fase 3: Generación"* — nomenclatura que además **colisiona** con las Fases 1–4 del roadmap del README, que significan otra cosa.

**Impacto.** Un lector que empiece por `ARCHITECTURE.md` construye un modelo mental equivocado del sistema y llega a `PAPER.md` con expectativas contradictorias. Para un repositorio de portafolio, es el documento con más probabilidad de ser abierto en primer lugar tras el README.

**Reproducción.** Comparar `ARCHITECTURE.md` §2 con `src/services/ingestion.py:48`, y §3 con `src/services/retriever.py:34`.

**Parche.** Banner al inicio del archivo, mínimo viable:

```markdown
> ⚠️ **Documento histórico (Fases 1–2).** Describe el pipeline lineal original,
> sustituido en la Fase 4 por la arquitectura multi-agente. Se conserva como
> registro de la evolución del proyecto.
> Para la arquitectura vigente, ver **[docs/PAPER.md](docs/PAPER.md)**.
```

Alternativa preferible: reescribirlo como resumen técnico de la arquitectura actual —el hueco que hoy solo cubre un paper de 478 líneas— y mover el contenido histórico a `docs/ARCHITECTURE_FASE_1.md`.

---

### `DOC-06` 🟡 Chunking: 400 tokens en código vs 500 en el paper

**Lo que dice la documentación.**

`PAPER.md` §5.2:
> *"…o si la acumulación de tokens del chunk actual supera el límite superior estricto $L_{max} = 500$ tokens (Línea 26)."*

`PAPER_PLAN.md` §3.9: *"o acumulación de tokens del chunk excede `max_tokens=500`"*.

**Lo que hace el código.** `src/services/ingestion.py:48`:

```python
def chunk_text(content: str, source_type: str, max_tokens: int = 400, overlap: int = 0) -> List[DocumentChunk]:
```

y la condición de ruptura real (l. 91):

```python
if dist > threshold or (current_chunk_tokens + tokens_count) > max_tokens:
```

**Divergencia adicional: el parámetro `overlap` es código muerto.** Se declara con default `0` y **nunca se lee** en el cuerpo de la función. Es un residuo de la implementación de tamaño fijo de la Fase 1 (que sí usaba overlap 30, según `ARCHITECTURE.md` §2). Su presencia sugiere que el semantic chunking soporta solapamiento — no lo hace.

**Divergencia adicional: las referencias de línea del paper están desfasadas.** El paper cita ubicaciones concretas que ya no corresponden:

| Cita del paper | Línea real |
|---|---|
| §5.1: *"líneas 33-34"* para la fórmula RRF en `retriever.py` | 54 |
| §5.2: *"líneas 18-20"* para `cosine_distance` | 39-45 |
| §5.2: *"Línea 23"* para el umbral $\tau$ | 78 |
| §5.2: *"Línea 26"* para el límite de tokens | 91 |
| §5.4: *"Línea 10"* para `route_reviewer` en `graph.py` | 11-18 |
| §5.6: *"Líneas 42-44"* para los `CHECK` en `01_init.sql` | 64-66 |

**Lo que sí es correcto.** El resto de la formalización de §5.2 es exacta: la fórmula de distancia coseno, el umbral $\tau = \mu + 1.25\sigma$ (`ingestion.py:78`), y la condición de ruptura disyuntiva. Solo la constante y las líneas divergen.

**Reproducción.**

```bash
grep -n "max_tokens\|overlap" src/services/ingestion.py | head -5
grep -n "500\|L_{max}" docs/PAPER.md | head -3
```

**Parche.** Decidir cuál es el valor correcto —`400` está en el código y es lo que se ejecuta— y alinear ambos papers. Eliminar el parámetro muerto:

```diff
-def chunk_text(content: str, source_type: str, max_tokens: int = 400, overlap: int = 0) -> List[DocumentChunk]:
+def chunk_text(content: str, source_type: str, max_tokens: int = 400) -> List[DocumentChunk]:
```

Para las referencias de línea: citar por **nombre de función** en lugar de por número. `(`chunk_text`, condición de ruptura)` no envejece; `(Línea 26)` envejece en el siguiente commit. Es la causa raíz de seis divergencias de este hallazgo.

---

### `DOC-07` 🟡 Modelo LLM mal citado en toda la documentación

**Lo que dice la documentación.**

- `README.md`, badge: `![Anthropic](https://img.shields.io/badge/LLM-Claude%20Haiku-purple.svg)`
- `README.md` §Stack: *"`Anthropic Claude 3.5 Haiku` + `Instructor` + `Pydantic v2`"*
- `src/services/extractor.py:40`, comentario: *"# Claude 3.5 Haiku o Sonnet son ideales para esto."*

**Lo que hace el código.** Las siete llamadas usan `claude-haiku-4-5-20251001`:

| Archivo:línea | Función | `max_tokens` |
|---|---|:---:|
| `router.py:75` | `analyze_query` | 500 |
| `extractor.py:42` | `generate_answer` | 8192 |
| `extractor.py:77` | `generate_answer_stream` (muerta) | 8192 |
| `memory.py:37` | `extract_and_save_facts` | 200 |
| `graphrag.py:36` | `extract_knowledge_graph` | 1024 |
| `evaluator.py:59` | `evaluate_rag_response` | 300 |
| `ingestion.py:118` | `describe_image_with_claude` | 1000 |

**Análisis.** El comentario de `router.py:72-73` documenta la decisión real:

```python
# Usamos claude-haiku-4-5-20251001 que descubrimos que funciona perfecto en tu cuenta
# Haiku es súper rápido y barato, ideal para ruteo
```

La elección es correcta y está bien justificada. Lo que falla es la documentación pública, que cita un modelo de una generación anterior.

**Problema de mantenimiento asociado.** El identificador está **repetido literalmente siete veces**. Cualquier migración de modelo requiere siete ediciones coordinadas, con riesgo de dejar módulos desalineados. Es exactamente el tipo de acoplamiento que el resto del proyecto evita (los umbrales, en cambio, sí están centralizados como defaults de función).

**Reproducción.**

```bash
grep -rn "claude-haiku" src/ | wc -l          # 7
grep -rn "3.5 Haiku\|Claude 3.5" README.md src/  # README §Stack + extractor.py:40
```

**Parche.** Centralizar y corregir. Crear `src/services/llm_config.py`:

```python
import os

# Modelo por defecto para todas las tareas del sistema.
# Haiku: latencia baja y coste reducido, suficiente para ruteo, extracción y evaluación.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
```

Los siete puntos pasan a `model=ANTHROPIC_MODEL`. Actualizar el badge y la sección de stack del README, y el comentario de `extractor.py:40`.

Con la variable de entorno, además, se puede probar un modelo más capaz en el generador sin tocar código — útil para el trade-off que `PAPER.md` §9 discute.

---

### `DOC-08` ⚪ Python 3.12 (badge) vs 3.14 (`requires-python`)

**Lo que dice el `README.md`.** Badge: `![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)`. Sección de stack: *"Backend Framework: `FastAPI` (Python 3.12+, asíncrono puro)"*.

**Lo que exige el build.** `pyproject.toml:3`:

```toml
requires-python = ">=3.14"
```

El entorno verificado corre Python 3.14.0.

**Impacto.** Un usuario con Python 3.12 —que cumple exactamente lo que el README pide— falla en `uv sync` con un error de resolución de versión. Es el primer paso de las instrucciones de instalación.

**Reproducción.**

```bash
grep -n "requires-python" pyproject.toml    # 3: >=3.14
grep -n "3.12" README.md                     # badge + sección de stack
```

**Parche.** Alinear el badge y la sección a `3.14+`, o relajar `requires-python` a `>=3.12` si no hay dependencia real de características de 3.13/3.14 (no se detectó ninguna en el código: no hay sintaxis exclusiva de esas versiones). La segunda opción amplía la base de usuarios que pueden ejecutar el proyecto; la primera es más honesta con el entorno probado.

---

## 8. Higiene del Repositorio

### `HYG-01` 🟡 Dependencias directas no declaradas

**Análisis.** Tres paquetes se importan en el código pero **no figuran en `pyproject.toml`**:

| Paquete | Importado en | Uso | Llega por |
|---|---|---|---|
| `pyjwt` | `src/api/auth.py:6` (`import jwt`) | Firma y verificación de tokens | transitiva |
| `numpy` | `src/services/ingestion.py:37` | `mean`, `std`, `dot`, `linalg.norm` en el chunking | transitiva de `sentence-transformers` |
| `python-multipart` | requerido por `UploadFile` en `src/api/routers/ingest.py:14` | Parseo de formularios multipart | transitiva de `fastapi` |

Verificado en el entorno: `pyjwt` 2.13.0, `numpy` 2.5.2, `python-multipart` 0.0.32 — instalados, pero no por declaración propia.

**Impacto.** Funcionan solo mientras alguna otra dependencia siga arrastrándolos. Si `sentence-transformers` cambiara su backend a uno sin `numpy` explícito, o si `fastapi` moviera `python-multipart` a un extra opcional, el fallo sería en tiempo de ejecución (`ImportError` en el arranque para `pyjwt`; `RuntimeError: Form data requires "python-multipart"` en el primer upload) sin ningún cambio en el código propio.

**Problema inverso: dependencia pesada innecesaria.** `deepeval==4.2.1` está declarada como dependencia **de producción**, pero su único consumidor (`tests/test_rag.py`) está roto (`BUG-07`). Arrastra un árbol considerable a la imagen final. Lo mismo aplica a `pytest>=9.1.1`.

Además falta `pytest-asyncio`, sin el cual el `@pytest.mark.asyncio` de `tests/test_rag.py:18` no tiene efecto —los tests async se saltarían silenciosamente incluso si se arreglara `BUG-07`.

**Contradicción menor.** `CONTEXT.md` §Reglas de Codificación establece: *"Cero dependencias pesadas innecesarias (usar `flashrank` en lugar de `torch`)"*. La regla es buena y `flashrank` la cumple, pero `sentence-transformers` arrastra `torch` de todos modos, y `deepeval` añade otro árbol sin uso.

**Reproducción.**

```bash
grep -iE "jwt|numpy|multipart|pytest-asyncio" pyproject.toml   # sin coincidencias
grep -rn "^import jwt\|^import numpy\|import numpy as np" src/
```

**Parche.**

```diff
 dependencies = [
     "anthropic==1.4.0",
     "asyncpg>=0.31.0",
-    "deepeval==4.2.1",
     "fastapi>=0.141.1",
     "flashrank>=0.2.10",
     "instructor>=1.16.0",
     "langchain-core>=1.6.2",
     "langfuse>=4.15.1",
     "langgraph>=1.2.11",
+    "numpy>=2.0",
     "pillow>=12.3.0",
     "pydantic>=2.13.5",
+    "pyjwt>=2.10",
     "pymupdf>=1.28.2",
-    "pytest>=9.1.1",
     "python-dotenv>=1.2.3",
+    "python-multipart>=0.0.20",
     "requests>=2.34.2",
     "sentence-transformers>=6.0.1",
     "streamlit==1.63.0",
     "tiktoken>=0.14.0",
     "uvicorn>=0.52.4",
 ]
+
+[dependency-groups]
+dev = [
+    "deepeval==4.2.1",
+    "pytest>=9.1.1",
+    "pytest-asyncio>=0.24",
+]
```

**Nota sobre los pines sin commitear.** El diff pendiente en el árbol de trabajo fija tres versiones exactas (`anthropic==1.4.0`, `deepeval==4.2.1`, `streamlit==1.63.0`) donde antes había rangos. Fijar es defendible para reproducibilidad, pero conviene que sea una decisión consciente y documentada, no un residuo de depuración — y `uv.lock` ya garantiza la reproducibilidad exacta por sí solo.

---

### `HYG-02` 🟡 Código muerto versionado en la raíz

**Análisis.** Nueve archivos que `PAPER_PLAN.md` §5.2 ya identifica como *"scripts iterativos de validación local del desarrollador (código muerto/experimentos)"* siguen versionados:

| Archivo | Ubicación | Estado |
|---|---|---|
| `test_chunk.py` | raíz | script de validación local |
| `test_db.py` | raíz | script de validación local |
| `test_sim.py` | raíz | script de validación local |
| `test_sse.py` | raíz | script de validación local |
| `scratch_db.py` | raíz | experimento |
| `scratch_stream.py` | raíz | experimento |
| `src/pipeline.py` | `src/` | pipeline de la Fase 1, roto (`TypeError`, igual que `BUG-07`) |
| `src/models/requests.py:10-11` | — | `IngestRequest` nunca usada |
| `uvicorn.log` | raíz | log de ejecución (ver `HYG-03`) |

**Impacto específico de los `test_*.py` en la raíz.** `pytest` los descubre por convención de nombre. Un `uv run pytest` desde la raíz intenta recolectarlos junto a `tests/test_rag.py`, mezclando scripts de exploración con la suite real. Como varios ejecutan código a nivel de módulo (conexiones a base de datos, carga de modelos), la recolección misma tiene efectos secundarios.

**Impacto en la lectura del repositorio.** Para un repositorio de portafolio, nueve archivos muertos en la raíz son lo primero que ve alguien que hace `ls`. Compiten visualmente con los cinco archivos que sí importan.

**Reproducción.**

```bash
ls *.py
# scratch_db.py  scratch_stream.py  test_chunk.py  test_db.py  test_sim.py  test_sse.py
```

**Parche.** Borrarlos —el historial de git los conserva íntegros y son recuperables con `git log --all --diff-filter=D`:

```bash
git rm test_chunk.py test_db.py test_sim.py test_sse.py scratch_db.py scratch_stream.py
git rm src/pipeline.py          # o repararlo si se quiere conservar como demo de la Fase 1
git rm --cached uvicorn.log
```

Si se prefiere conservarlos, moverlos a `scratch/` (fuera del path de descubrimiento de pytest) con un `README` de una línea explicando qué son.

Eliminar también `IngestRequest` de `src/models/requests.py`.

---

### `HYG-03` ⚪ `.gitignore` incompleto

**Contenido actual:**

```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.DS_Store
```

**Lo que falta.** Dos elementos están versionados y no deberían:

1. **`.idea/`** — 9 archivos de configuración de PyCharm, incluido `workspace.xml`, que contiene estado local del editor (archivos abiertos, posición del cursor, historial de ejecuciones). Cambia en cada sesión y genera ruido constante en `git status`.
2. **`uvicorn.log`** (153 B) — log de ejecución.

Faltan además entradas preventivas: `/tmp/flashrank` está fuera del repo (`reranker.py:10` usa `cache_dir="/tmp/flashrank"`), pero el caché de `sentence-transformers` (`~/.cache/huggingface`) también, así que no hay riesgo inmediato. Sí convendría cubrir artefactos de build (`dist/`, `*.egg-info/`) y de cobertura (`.coverage`, `htmlcov/`) si se añade CI.

**Reproducción.**

```bash
git ls-files | grep -E "\.idea|\.log"
```

**Parche.**

```diff
 .env
 .venv/
 __pycache__/
 *.pyc
 .pytest_cache/
 .DS_Store
+
+# IDE
+.idea/
+.vscode/
+
+# Logs y artefactos
+*.log
+dist/
+*.egg-info/
+.coverage
+htmlcov/
```

Y retirarlos del índice: `git rm -r --cached .idea uvicorn.log`.

---

### `HYG-04` ⚪ `datetime.utcnow()` deprecado

**Ubicación.** `src/api/auth.py:38-46`

```python
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta        # ← l. 41
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)  # ← l. 43
```

**Análisis.** `datetime.utcnow()` está deprecado desde Python 3.12. El proyecto exige 3.14 (`DOC-08`), donde emite `DeprecationWarning` en cada emisión de token.

El problema de fondo es que devuelve un `datetime` **naive** (sin `tzinfo`), lo que históricamente ha causado errores de comparación entre horas locales y UTC. Aquí no hay bug funcional —PyJWT convierte a timestamp Unix asumiendo UTC, que es lo correcto— pero el patrón es frágil.

**Reproducción.**

```bash
grep -n "utcnow" src/api/auth.py    # 41, 43
```

**Parche.**

```diff
-from datetime import datetime, timedelta
+from datetime import datetime, timedelta, timezone
@@
-        expire = datetime.utcnow() + expires_delta
+        expire = datetime.now(timezone.utc) + expires_delta
     else:
-        expire = datetime.utcnow() + timedelta(minutes=15)
+        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
```

---

### `HYG-05` 🟡 Tres servicios crean su cliente de Anthropic antes de cargar `.env`

> Posterior a la foto: encontrado el 2026-09-14 al verificar `BUG-02`. La nota de §3.3 lo señalaba solo para `evaluator.py` y sin catalogarlo.

**Ubicación.** Al importarse, sin haber llamado a `load_dotenv()`:

| Archivo:línea | Qué lee del entorno |
|---|---|
| `src/services/router.py:10` | `ANTHROPIC_API_KEY` |
| `src/services/extractor.py:13` | `ANTHROPIC_API_KEY` |
| `src/services/evaluator.py:12` | `ANTHROPIC_API_KEY` y, en la l. 11, `DATABASE_URL` |

**Análisis.** Funcionan solo porque `src/api/main.py` importa antes módulos que sí cargan `.env` (`auth.py`, `cache.py`, `memory.py`…). Cualquier punto de entrada que importe primero el grafo o estos servicios crea los clientes sin clave: un script, un test, un worker. Y el fallo no aparece al importar, sino en la primera llamada al LLM. `evaluator.py`, además, caería al DSN por defecto.

**Evidencia.** Verificando `BUG-02`, un lanzador que importaba `src.services.agent_graph.nodes` antes que `src.api.main` hizo fallar las 11 peticiones con *"Could not resolve authentication method. Expected either api_key or auth_token to be set"*. Cargar `.env` antes de cualquier import lo resolvió.

**Reproducción.**

```bash
for f in src/services/*.py; do
  grep -q "AsyncAnthropic(" "$f" && ! grep -q "load_dotenv()" "$f" && echo "$f"
done
# src/services/evaluator.py, src/services/extractor.py, src/services/router.py
```

**Parche.** Un único `src/config.py` que llame a `load_dotenv()` y exponga las variables, importado por todos los servicios antes de leer el entorno. Otra opción es crear los clientes de forma perezosa en la primera llamada. Encaja con el `ANTHROPIC_MODEL` único que propone `DOC-07`.

---

### `HYG-06` ⚪ La base de datos no se reinicia con Docker

> Posterior a la foto: encontrado el 2026-09-14 durante la verificación de `BUG-05`.

**Ubicación.** `docker-compose.yml`: el servicio `postgres` no declara `restart`.

**Análisis.** Tras reiniciar Docker Desktop o el equipo, el contenedor queda parado y la API falla con conexión rechazada en el puerto 5433, sin que nada indique por qué.

**Evidencia.** El 2026-09-14 a las 17:37:52 UTC, Docker Desktop se reinició a mitad de una verificación. Los tres contenedores en ejecución se detuvieron en el mismo instante. Los dos que tenían política de reinicio volvieron solos; el del sandbox no. El apagado fue limpio y no se perdieron datos.

**Parche.**

```yaml
  postgres:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
```

---

### `HYG-07` 🟡 `ALTER DEFAULT PRIVILEGES` regala a `app_user` cualquier tabla futura de `public`

> Posterior a la foto: encontrado el 2026-09-15 al implementar `SEC-05`.

**Ubicación.** `sql/00_create_app_user.sql:5`.

```sql
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO app_user;
```

**Análisis.** No concede permisos sobre las tablas de hoy, sino sobre todas las que el superusuario cree mañana en `public`. Cualquier tabla nueva nace con un `GRANT ALL` explícito a favor de `app_user`, incluidas las que se creen precisamente para que el rol de la aplicación no las lea. Y como el permiso es un `GRANT` al rol, no a `PUBLIC`, un `REVOKE ALL ... FROM PUBLIC` no lo retira: hay que revocar al rol por su nombre, o crear la tabla fuera de `public`.

Las dos líneas anteriores del mismo script (`GRANT ... ON ALL TABLES` y `ON ALL SEQUENCES`) se ejecutan antes de que exista ninguna tabla, así que no hacen nada; los permisos reales de la aplicación los concede `sql/01_init.sql` al final, tabla por tabla. Esta línea es, por tanto, prescindible.

**Evidencia.** La primera versión del parche de `SEC-05` guardaba la clave de firma en `public.tenant_signing_key` con `REVOKE ALL ON TABLE ... FROM PUBLIC`. Contra una base recién creada desde volumen vacío, `has_table_privilege('app_user', 'tenant_signing_key', 'SELECT')` devolvió `true`, y como `app_user`:

```
SELECT key FROM tenant_signing_key;   -- b9f23fd87455c8eda71ebebafeaa4f94...
```

Con esa clave a la vista, `app_user` podía firmar cualquier tenant y `SEC-05` quedaba sin efecto pese a pasar el resto de las pruebas de aislamiento.

**Reproducción.**

```sql
-- como postgres
CREATE TABLE secreta (dato TEXT);
REVOKE ALL ON TABLE secreta FROM PUBLIC;
SELECT has_table_privilege('app_user', 'secreta', 'SELECT');   -- true
```

**Parche.** Borrar la línea (las cinco tablas de la aplicación ya reciben su `GRANT` explícito en `01_init.sql`). Mientras siga ahí, todo objeto que deba quedar fuera del alcance de `app_user` va en un esquema aparte, como hace ya la clave de `SEC-05` en `tenant_security`.

---

### `HYG-08` 🟠 Los datos de la base viven en un volumen anónimo

> Posterior a la foto: encontrado el 2026-09-16, al revisar el estado de Docker.

**Ubicación.** `docker-compose.yml`: el servicio `postgres` monta `./sql` en `/docker-entrypoint-initdb.d`, pero no declara nada para `/var/lib/postgresql/data`.

**Análisis.** La imagen `pgvector/pgvector:pg16` declara `VOLUME /var/lib/postgresql/data`, así que Docker crea un volumen **anónimo** en el primer arranque. Los datos persisten —sobreviven a `stop`/`start`—, pero en un volumen cuyo nombre es un hash, indistinguible de cualquier otro anónimo de la máquina y no referenciado desde el proyecto.

El riesgo no es perder datos por un fallo, sino por un comando rutinario:

| Acción | Efecto |
|---|---|
| `docker stop` / `start` | Los datos sobreviven |
| `docker compose down` | El contenedor desaparece y el volumen queda **huérfano**; un `up` posterior crea uno nuevo y vacío, y la base aparece vacía sin que nada falle |
| `docker compose down -v` | Los datos se borran, sin recuperación |
| `docker volume prune` | Se lleva los anónimos huérfanos |

Es el mismo patrón de `BUG-08` (caché del re-ranker en `/tmp`): estado que importa, guardado donde nadie lo declara.

**Evidencia.** Sobre el contenedor de desarrollo, con 41 horas en marcha:

```
$ docker inspect ai_engineer_sandbox-postgres-1 -f '{{range .Mounts}}...{{end}}'
bind   | origen=<repo>/sql | destino=/docker-entrypoint-initdb.d
volume | origen=5b179a9ea01f43aa9f977868ee27c1216570a8f846c5932cc53428eec304a9cd
       | destino=/var/lib/postgresql/data

$ docker inspect pgvector/pgvector:pg16 -f '{{json .Config.Volumes}}'
{"/var/lib/postgresql/data":{}}
```

`docker volume ls` no muestra ningún volumen con nombre del proyecto; hay 3 anónimos en la máquina. El comportamiento con `-v` sí está comprobado aquí: al hacer `down -v` del proyecto desechable usado en `SEC-05` y levantarlo de nuevo, la base nació vacía. El caso sin `-v` es comportamiento documentado de Compose, no verificado en esta máquina.

**Parche.** Declarar un volumen nombrado:

```yaml
services:
  postgres:
    volumes:
      - ./sql:/docker-entrypoint-initdb.d
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

**Atención al aplicarlo:** el cambio no migra nada. Al levantar con el volumen nombrado, Postgres arranca sobre un volumen vacío, ejecuta los scripts de inicialización y la base de desarrollo actual —22 documentos, 128 tripletas, 4 filas de caché, 3 de memoria— queda en el volumen anónimo, huérfano. Para conservarla hay que volcarla antes (`pg_dump`) y restaurarla después, o copiar el contenido del volumen. Es una operación sobre la única copia de esos datos, así que la decide el usuario.

**Estado:** ✅ corregido el 2026-09-16, a petición del usuario y con un respaldo previo verificado.

**Respaldo.** Antes de tocar nada: `pg_dump` de la base y `pg_dumpall --roles-only`, fuera del repositorio y con permisos `600`, porque el volcado incluye la clave HMAC de `SEC-05`. Se verificó restaurándolo en un Postgres desechable: 22 / 128 / 4 / 3 / 0, la clave intacta y el aislamiento en pie (128 filas con firma, 0 sin ella).

**Migración.** Con el volumen nombrado declarado, `compose up` lo creó con sus etiquetas y recreó el contenedor; se paró Postgres **comprobando explícitamente** que no seguía en marcha, y se copió el volumen anónimo —montado en solo lectura— sobre el nombrado. Resultado: 1019 ficheros en ambos lados, mismo `PG_VERSION`, dueño `999:999` y `diff -r` sin diferencias. Al arrancar, Postgres registró `database system was shut down at …` sin ninguna línea de recuperación, lo que confirma que la copia viene de un cierre limpio. Recuentos, clave y aislamiento, idénticos a los del respaldo. El volumen anónimo original se conserva, huérfano a propósito, hasta que el usuario decida borrarlo.

**Control negativo**, en dos proyectos desechables y con la misma secuencia —escribir una fila marca, `docker compose down` **sin** `-v`, `up` y leerla—:

| | Compose anterior (`HEAD`) | Compose corregido |
|---|---|---|
| Volumen de datos antes / después | `6b0d2ffb…` / `cb47e5f8…` (distinto) | `hyg08despues_pgdata` / el mismo |
| Fila marca tras `down` + `up` | `relation "marca_hyg08" does not exist` | `sobrevivo` |
| Volumen anterior | queda huérfano | — |

Esto verifica también el caso sin `-v`, que la evidencia de arriba daba solo como comportamiento documentado de Compose. Sigue siendo cierto que `down -v` y `docker volume prune` borran los datos: un volumen nombrado protege contra el descuido, no contra la orden explícita de borrar.

**Incidencia durante la migración.** El primer intento omitió la declaración de `volumes:` a nivel raíz. Compose rechazó el proyecto, pero el fallo quedó oculto porque cada orden iba en una tubería (`| tail`) y `set -e` solo mira el código del último comando de la tubería: el `stop` no llegó a ejecutarse y la copia se hizo con Postgres en marcha, sobre un volumen que `docker run` creó sin las etiquetas de Compose. No hubo daño —el origen iba en solo lectura y el contenedor de desarrollo siguió en marcha con 22 / 128 / 4 / 3 / 0 y sin errores en el log—, pero la copia en caliente se descartó y el proceso se repitió con `set -o pipefail` y comprobaciones explícitas antes de cada paso destructivo.

---

## 9. Traza End-to-End Anotada

Recorrido de una consulta real por el sistema, señalando dónde se activa cada hallazgo. Escenario: usuario autenticado como `bryan` envía *"¿Y en qué años trabajó con eso?"* como **segunda** pregunta de la conversación, tras haber preguntado por AWS.

| # | Paso | Ubicación | Hallazgos activos |
|:---:|---|---|---|
| 1 | Streamlit construye el payload con `query` + `history` (1 turno previo) | `frontend/app.py:87-88` | — |
| 2 | `POST /chat/stream/` con `Authorization: Bearer <jwt>` | `frontend/app.py:91` | — |
| 3 | `get_current_user` decodifica el token, extrae `tenant_id` como `str` sin validar | `auth.py:72-80` | 🔴 `SEC-01` 🔴 `SEC-02` |
| 4 | `check_semantic_cache`: abre conexión #1, `SET app.current_tenant` por f-string, busca similitud ≥ 0.85 | `chat.py:77` → `cache.py:21-41` | 🟠 `PERF-01` 🔴 `SEC-02` |
| 5 | *Si hubo hit:* devuelve respuesta con prefijo de progreso incrustado + `⚡ [CACHE HIT]` y termina | `chat.py:79-81` | 🟠 `BUG-01` 🟠 `BUG-02` |
| 6 | `retrieve_user_facts`: conexión #2, top-3 hechos con similitud > 0.3, envueltos en `<USER_PROFILE>` | `chat.py:83` → `memory.py:70-95` | 🟠 `PERF-01` |
| 7 | Se construye `initial_state`. **`request.history` no se copia** | `chat.py:85-96` | 🟠 `BUG-03` |
| 8 | `supervisor_node` → `analyze_query(query, [])` con historial vacío | `nodes.py:18` | 🟠 `BUG-03` |
| 9 | Claude clasifica la intención **sin contexto previo**: "¿Y en qué años trabajó con eso?" es incomprensible aislada → probable `out_of_scope` o `knowledge_search` con variantes genéricas | `router.py:74-79` | 🟠 `BUG-03` 🟡 `DOC-07` |
| 10 | *Si `tool_execution`:* `requests.get()` síncrono bloquea el event loop hasta 5 s | `nodes.py:40` → `tools.py` | 🟡 `PERF-03` |
| 11 | `researcher_node`: 5 × `retrieve_documents` en `asyncio.gather` → **5 conexiones simultáneas**, `top_k=15` hardcodeado | `nodes.py:70-71` | 🟠 `PERF-01` 🟡 `BUG-06` 🔴 `SEC-02` |
| 12 | Deduplicación por `content` exacto sobre ~75 candidatos | `nodes.py:74-80` | ✅ correcto |
| 13 | `rerank_documents` con FlashRank, `top_k=10` hardcodeado (contrato dice 7) | `nodes.py:83` | 🟡 `BUG-06` |
| 14 | `retrieve_subgraph`: conexión #7, `WHERE` concatenado, *seq scan* completo | `nodes.py:86` → `graphrag.py:78-89` | 🟠 `SEC-03` 🟠 `PERF-01` |
| 15 | Sub-grafo inyectado en índice 0, saltándose el reranker | `nodes.py:87-93` | ✅ correcto y bien documentado |
| 16 | `generator_node` → `generate_answer` (**no** `generate_answer_stream`) | `nodes.py:107` | 🟠 `DOC-01` |
| 17 | Claude genera la respuesta completa; `max_tokens=8192` | `extractor.py:41-48` | 🟡 `DOC-07` |
| 18 | `route_reviewer`: si `requires_more_info` → vuelve a `researcher` **con las mismas queries** | `graph.py:11-18` | 🟡 `BUG-05` |
| 19 | *Si reiteró:* +6 conexiones, +1 llamada LLM, resultado idéntico | `nodes.py:61-95` | 🟡 `BUG-05` 🟠 `PERF-01` |
| 20 | SSE emite 4 eventos discretos, no tokens | `chat.py:102-120` | 🟠 `DOC-01` |
| 21 | `final_dict["answer"] = accumulated_answer + respuesta` | `chat.py:119` | 🟠 `BUG-01` |
| 22 | `save_semantic_cache` persiste el dict **contaminado**, conexión #8 | `chat.py:123` | 🟠 `BUG-01` 🟠 `PERF-01` |
| 23 | `extract_and_save_facts` en background: LLM + conexión #9 | `chat.py:124` → `memory.py:36-62` | 🟠 `PERF-01` |
| 24 | `evaluate_rag_response` en background: recibe la respuesta contaminada, `max_tokens=300`, sin `ge`/`le`, conexión #10 | `chat.py:127` → `evaluator.py` | 🟠 `BUG-01` 🟡 `PERF-04` 🟠 `DOC-02` 🟠 `PERF-01` |
| 25 | Si el evaluador truncó o devolvió un score fuera de rango: excepción absorbida, evaluación perdida sin traza | `evaluator.py:86` | 🟡 `PERF-04` 🟠 `DOC-02` |

**Conteo de conexiones de esta traza:** 10 sin reintento, 16 con reintento.

**Observación.** El paso 9 es donde `BUG-03` produce su daño real: una pregunta de seguimiento perfectamente natural es irresoluble porque el supervisor no ve el turno anterior. Todos los pasos posteriores trabajan correctamente sobre una interpretación equivocada de la pregunta.

---

## 10. Plan de Remediación

Ordenado por relación impacto/esfuerzo. Las estimaciones son de implementación, sin incluir pruebas.

### Avance al 2026-09-14

| Bloque | Estado |
|---|---|
| 0 — Desbloqueo | ✅ cerrado (`BUG-08`) |
| 1 — Seguridad | ✅ cerrado (`SEC-01` a `SEC-04`) |
| 2 — Corrección funcional | ✅ cerrado (`BUG-01` a `BUG-06`, más `BUG-09`) |
| 3 — Rendimiento | ✅ cerrado (`PERF-01` a `PERF-04`, 2026-09-15) |
| 4 — Reconciliación documental | ⬜ abierto (`DOC-01` y `DOC-02` ya corregidos) |
| 5 — Higiene y cobertura | ⬜ abierto |

Los hallazgos posteriores a la foto, con el bloque en que encajan:

| # | Acción | Hallazgo | Bloque | Esfuerzo |
|:---:|---|---|:---:|:---:|
| 29 | ✅ hecho (2026-09-15). Contexto de tenant firmado con HMAC, verificado por una función `SECURITY DEFINER` | `SEC-05` | 3, con el paso 12 | 2–4 h |
| 34 | Acotar el `ALTER DEFAULT PRIVILEGES` sobre `public` a las cinco tablas de la aplicación | `HYG-07` | 5 | 15 min |
| 35 | ✅ hecho (2026-09-16). Volumen nombrado para los datos, con respaldo verificado y migración en frío de la base actual | `HYG-08` | 5 | 30 min |
| 30 | ✅ hecho (2026-09-15). Mensaje genérico con identificador al cliente; el detalle, solo en el log | `SEC-06` | 1 | 20 min |
| 31 | ✅ hecho (2026-09-16). No usar el caché cuando la petición trae historial | `BUG-10` | 2 | 15 min |
| 32 | `src/config.py` con `load_dotenv()` antes de crear clientes | `HYG-05` | 5 | 20 min |
| 33 | `restart: unless-stopped` en el servicio `postgres` | `HYG-06` | 5 | 2 min |
| D-01, D-02 | Limpiezas de datos pendientes de decisión (tabla de §1) | `SEC-04`, `BUG-02` | — | 5 min |

Las comprobaciones de las correcciones de los bloques 0 a 2 se ejecutaron desde scripts fuera del repositorio: controles negativos contra el servidor real y casos directos de ruteo, ventana de recuperación, política de caché y validación. Lo que tienen de reproducible está en la línea de estado de cada hallazgo y en el mensaje de su commit. Convertir en tests versionados los casos que no necesitan base de datos ni LLM es parte del paso 28 (`BUG-07`).

### Bloque 0 — Desbloqueo (prerrequisito de todo lo demás)

| # | Acción | Hallazgo | Archivos | Esfuerzo |
|:---:|---|---|---|:---:|
| 0 | Mover el caché de FlashRank fuera de `/tmp` y sanear directorios sin modelo | `BUG-08` | `reranker.py` | 10 min |

Sin esto la API no arranca en cuanto `/tmp` se vacía, y ningún otro bloque es verificable.

### Bloque 1 — Seguridad (bloqueante antes de cualquier despliegue)

| # | Acción | Hallazgo | Archivos | Esfuerzo |
|:---:|---|---|---|:---:|
| 1 | `SECRET_KEY` a variable de entorno, sin default | `SEC-01` | `auth.py`, `.env.example` | 5 min |
| 2 | Tipar `User.tenant_id` como `uuid.UUID` | `SEC-02` | `auth.py` | 5 min |
| 3 | `NamedTemporaryFile` en la ingesta | `SEC-04` | `ingest.py` | 10 min |
| 4 | `ILIKE ANY($1::text[])` parametrizado en GraphRAG | `SEC-03` | `graphrag.py` | 10 min |

Los cuatro cierran las dos vulnerabilidades críticas y las dos altas en **media hora**. Es el bloque con mayor retorno del documento.

### Bloque 2 — Corrección funcional

| # | Acción | Hallazgo | Archivos | Esfuerzo |
|:---:|---|---|---|:---:|
| 5 | Separar objeto de stream del objeto que se cachea | `BUG-01` | `chat.py` | 15 min |
| 6 | `DELETE` de las filas de caché ya contaminadas | `BUG-01` | SQL puntual | 5 min |
| 7 | No cachear `tool_execution`, `out_of_scope` ni baja confianza | `BUG-02` | `chat.py` | 20 min |
| 8 | Propagar `history` hasta `analyze_query` | `BUG-03` | `state.py`, `chat.py`, `nodes.py` | 30 min |
| 9 | Reordenar los scripts SQL; añadir `knowledge_graph` y `FORCE` a `01_init.sql` | `BUG-04` | `sql/`, `docker-compose.yml` | 30 min |
| 10 | Propagar `top_k_retrieve` / `top_k_rerank` | `BUG-06` | `state.py`, `chat.py`, `nodes.py` | 15 min |
| 11 | Decidir sobre el ciclo: ampliar búsqueda en reintentos, o desactivar | `BUG-05` | `nodes.py`, `graph.py` | 1 h |

El paso 6 es **prerrequisito** del 5: sin él, las filas envenenadas siguen sirviéndose aunque el código ya no las genere.

### Bloque 3 — Rendimiento

| # | Acción | Hallazgo | Archivos | Esfuerzo |
|:---:|---|---|---|:---:|
| 12 | Pool de conexiones en el `lifespan` + `set_config` local a transacción | `PERF-01`, `SEC-02` | `main.py` + 6 servicios | 2 h |
| 13 | Módulo `embeddings.py` con instancia única y `to_pgvector` | `PERF-02` | nuevo + 4 servicios | 30 min |
| 14 | `asyncio.to_thread` sobre `chunk_text` y sobre las tools | `PERF-03` | `ingestion.py`, `nodes.py` | 15 min |
| 15 | `max_tokens=1024` y `max_length` en `reasoning` | `PERF-04` | `evaluator.py` | 5 min |

El paso 12 debe hacerse **junto** a la corrección de `SEC-02`: con pool, `SET app.current_tenant` persiste entre usos de la misma conexión y se convierte en un vector de fuga entre tenants si no se acota a la transacción. Ver la nota al final de `PERF-01`.

### Bloque 4 — Reconciliación documental

| # | Acción | Hallazgo | Archivos |
|:---:|---|---|---|
| 16 | Decidir sobre el streaming: reimplementar con `astream_events`, o reescribir README y marcar `TROUBLESHOOTING.md` §4-5 | `DOC-01` | `chat.py` o `README.md` |
| 17 | Añadir `ge=0.0, le=1.0` a `RAGEvaluation` (alinea código con paper) | `DOC-02` | `evaluator.py` |
| 18 | ✅ hecho (2026-09-16). Reescribir `.env.example`; banner histórico en `CONTEXT.md`; en el README, rellenar `.env` antes de levantar la base | `DOC-03` | `.env.example`, `CONTEXT.md`, `README.md` |
| 19 | Corregir la mención a NetworkX y remitir al roadmap | `DOC-04` | `README.md` |
| 20 | Banner de documento histórico en `ARCHITECTURE.md` | `DOC-05` | `ARCHITECTURE.md` |
| 21 | Alinear 400/500 tokens; eliminar `overlap`; citar por función, no por línea | `DOC-06` | `PAPER.md`, `PAPER_EN.md`, `ingestion.py` |
| 22 | Constante `ANTHROPIC_MODEL` única; corregir "Claude 3.5 Haiku" | `DOC-07` | nuevo + 7 llamadas + `README.md` |
| 23 | Alinear el badge de Python con `requires-python` | `DOC-08` | `README.md` o `pyproject.toml` |

### Bloque 5 — Higiene y cobertura

| # | Acción | Hallazgo |
|:---:|---|---|
| 24 | Declarar `pyjwt`, `numpy`, `python-multipart`; mover `deepeval`/`pytest` a `dev`; añadir `pytest-asyncio` | `HYG-01` |
| 25 | Borrar los 9 archivos muertos y `IngestRequest` | `HYG-02` |
| 26 | Ampliar `.gitignore`; `git rm --cached .idea uvicorn.log` | `HYG-03` |
| 27 | `datetime.now(timezone.utc)` | `HYG-04` |
| 28 | Reparar o retirar `tests/test_rag.py`; añadir tests unitarios de `chunk_text` y de las funciones de ruteo | `BUG-07` |

El paso 28 tiene valor propio: tests unitarios de `route_supervisor` / `route_reviewer` sobre diccionarios construidos a mano capturarían `BUG-05` como regresión y no requieren base de datos ni API.

### Resumen de esfuerzo

| Bloque | Esfuerzo estimado | Prioridad |
|---|:---:|---|
| 1 — Seguridad | ~30 min | **Bloqueante** |
| 2 — Corrección funcional | ~2,5 h | Alta |
| 3 — Rendimiento | ~3 h | Alta |
| 4 — Documentación | ~2 h | Media (alta para portafolio) |
| 5 — Higiene | ~1,5 h | Media |
| **Total** | **~9,5 h** | |

---

## 11. Anexo A: Matriz de Trazabilidad Documento ↔ Código

**Leyenda:** ✅ verificado en código · ⚠️ parcialmente cierto o matizado · ❌ divergente

### `README.md`

| Afirmación | Estado | Hallazgo |
|---|:---:|---|
| Streaming SSE con `Instructor` en tiempo real | ❌ | `DOC-01` |
| GraphRAG con NetworkX | ❌ | `DOC-04` |
| Claude 3.5 Haiku | ❌ | `DOC-07` |
| Python 3.12+ | ❌ | `DOC-08` |
| `cp .env.example .env` + `ANTHROPIC_API_KEY` | ❌ | `DOC-03` |
| Ciclos de razonamiento con "consultas más profundas" | ❌ | `BUG-05` |
| Function Calling determinista (3 herramientas) | ⚠️ | funciona una vez; luego `BUG-02` |
| Multi-Tenancy por RLS | ⚠️ | implementado, anulado por `SEC-01` |
| Caché semántico (`cos_distance < 0.15`) | ⚠️ | equivalente a similitud ≥ 0.85; redacción distinta |
| Two-Stage Retrieval (RRF + Cross-Encoder) | ✅ | — |
| Semantic Chunking por similitud coseno iterativa | ✅ | constante divergente (`DOC-06`) |
| HyDE y Multi-Query en el supervisor | ✅ | — |
| Evaluador LLM-as-a-judge en 3 dimensiones | ✅ | `DOC-02`, `PERF-04` sobre su robustez |
| Trazabilidad con Langfuse (`@observe`) | ✅ | 12 funciones instrumentadas |

### `PAPER.md` / `PAPER_EN.md`

| Sección | Afirmación | Estado | Hallazgo |
|---|---|:---:|---|
| §5.1 | RRF con $k=60$, fusión `FULL OUTER JOIN`, `top_k=15` | ✅ | líneas citadas desfasadas (`DOC-06`) |
| §5.2 | $L_{max} = 500$ tokens | ❌ | `DOC-06` |
| §5.2 | Umbral $\tau = \mu + 1.25\sigma$ | ✅ | — |
| §5.2 | Fórmula de distancia coseno | ✅ | — |
| §5.3 | HNSW `m=16`, `ef_construction=64` | ✅ | defaults de pgvector, correcto |
| §5.3 | Umbral de caché 0.85 | ✅ | — |
| §5.3 | Vectores de MiniLM normalizados ($\|v\|=1$) | ✅ | — |
| §5.4 | Máquina de estados $\mathcal{M}$, límite $\mathcal{O}(2)$ | ⚠️ | el límite es correcto; el ciclo no aporta información (`BUG-05`) |
| §5.5 | Deduplicación por hash de `content` | ✅ | — |
| §5.5 | $\mathcal{O}(\max T_{retrieval})$ "acotado por el pool `asyncpg`" | ❌ | `PERF-01` — no hay pool |
| §5.5 | GraphRAG ingenuo, 1-hop, `LIMIT 10`, regex `\w+` | ✅ | descripción honesta |
| §5.6 | Restricciones Pydantic `ge`/`le` en el evaluador | ❌ | `DOC-02` |
| §4.3.1 | El supervisor resuelve correferencias | ❌ | `BUG-03` |
| §4.3.2 | El investigador no invoca LLM, solo concurrencia | ✅ | — |
| §4.4 | Aislamiento multi-tenant por RLS | ⚠️ | anulado por `SEC-01` |
| §8.2 | Ausencia de benchmarks sistémicos | ✅ | limitación reconocida |
| §9.2 | Parche del modelo de FlashRank por 404 | ✅ | `ms-marco-MiniLM-L-12-v2` confirmado |
| §10.1-10.4 | Limitaciones: BM25 monolingüe, GraphRAG plano, caché sin TTL, sin Dockerfile | ✅ | correctas y honestas |

### `ARCHITECTURE.md`

| Afirmación | Estado | Hallazgo |
|---|:---:|---|
| Chunking 256 tokens / overlap 30 con `tiktoken` | ❌ | `DOC-05` |
| Retriever puramente vectorial | ❌ | `DOC-05` |
| Reranker `ms-marco-TinyBERT-L-2-v2` | ❌ | `DOC-05` |
| Pipeline lineal de 3 fases | ❌ | `DOC-05` |
| Evals con DeepEval en `tests/` | ❌ | `BUG-07` |
| Contratos Pydantic (`SearchResult`, `RerankedResult`, `StructuredAnswer`) | ✅ | siguen vigentes |
| Instructor parchea el cliente Anthropic con reintento por validación | ✅ | — |

### `CONTEXT.md`

| Afirmación | Estado | Hallazgo |
|---|:---:|---|
| Stack sobre OpenAI (`gpt-4o-mini`, `text-embedding-3-small`) | ❌ | `DOC-03` |
| Estado actual: solo `extractor`, `retriever`, `reranker` | ❌ | congelado en Fase 1 |
| Regla: todo I/O asíncrono | ⚠️ | `PERF-03` es la excepción |
| Regla: instrumentar con `@observe` | ✅ | 12 funciones |
| Regla: cero dependencias pesadas | ⚠️ | `deepeval` sin uso (`HYG-01`) |

### `GRAPHRAG_ARCHITECTURE.md`

| Afirmación | Estado | Hallazgo |
|---|:---:|---|
| Tabla `knowledge_graph` con RLS y `ON DELETE CASCADE` | ✅ | en `apply_graphrag.sql`, no en `01_init.sql` (`BUG-04`) |
| Extracción de tripletas con Instructor + Pydantic | ✅ | — |
| Normalización a minúsculas | ✅ | `graphrag.py:58` |
| Ingestión concurrente con `asyncio.gather` | ✅ | `ingestion.py:250-251` |
| Extracción de nodos semilla por palabras > 3 letras | ✅ | `SEC-03` sobre su construcción |
| Inyección en índice 0 sin pasar por el reranker, con justificación | ✅ | excelente decisión, bien argumentada |
| Modificación de `chat.py` para inyectar el subgrafo | ⚠️ | hoy vive en `nodes.py:86-93` tras la migración |

### `FASE_4_IMPLEMENTATION_DETAILS.md`

| Afirmación | Estado | Hallazgo |
|---|:---:|---|
| Caché semántico con umbral 0.85 y justificación empírica | ✅ | envenenado por `BUG-01`, sobre-aplicado por `BUG-02` |
| Memoria: extracción en background, top-3 hechos > 0.3 similitud | ✅ | — |
| Hechos en tercera persona, envueltos en `<USER_PROFILE>` | ✅ | — |
| Evaluador como `BackgroundTask` fire-and-forget | ✅ | `PERF-04`, `DOC-02` sobre su robustez |
| Diagrama de secuencia LangGraph + evaluador | ✅ | fiel al flujo real |

### `TROUBLESHOOTING.md`

| Sección | Afirmación | Estado | Hallazgo |
|---|---|:---:|---|
| §1 | Router con contexto del CV de Bryan | ✅ | `router.py:49` |
| §2 | `top_k_rerank` subido de 3 a 7 | ❌ | `BUG-06` — hoy hardcodeado a 10 |
| §2 | Deduplicación por `content` y 15 candidatos | ✅ | sobrevivió la migración |
| §3 | Cold start de modelos ML causa rechazos | ⚠️ | agravado 4× por `PERF-02`; `BUG-08` es una tercera causa del mismo síntoma |
| §4 | Streaming nativo con `st.write_stream()` | ⚠️ | el frontend sigue así; el backend ya no emite tokens (`DOC-01`) |
| §5 | `data.get("answer") or ""` para objetos parciales | ✅ | `app.py:115` |
| §6 | `max_tokens` subido a 2048 en el extractor | ✅ | hoy en 8192; el evaluador no recibió el mismo trato (`PERF-04`) |

### `PAPER_PLAN.md`

| Sección | Afirmación | Estado | Hallazgo |
|---|---|:---:|---|
| §1 | `01_init.sql` es un "script unificado" | ❌ | `BUG-04` — falta `knowledge_graph` y `FORCE` |
| §1 | `.env.example` con claves de Anthropic y JWT | ❌ | `DOC-03` |
| §3.9 | `max_tokens=500` en chunking | ❌ | `DOC-06` |
| §3.4 | Temperatura por defecto del modelo (1.0) | ✅ | ninguna llamada la fija |
| §3.7 | RRF con $k=60$ | ✅ | — |
| §3.11 | GraphRAG: regex `\w+`, `len>3`, `LIMIT 10` | ✅ | — |
| §5 | Inventario de 6 limitaciones conocidas | ✅ | correcto y honesto |

### `ROADMAP_FASE_5_ESCALABILIDAD.md`

| Epic | Estado | Observación |
|---|:---:|---|
| 1 — Contenerización total | ✅ | debe incorporar `BUG-04` (el compose no inicializa una base limpia) y `BUG-08` (el modelo del re-ranker debe hornearse en la imagen, no descargarse en cada arranque) |
| 2 — Dashboard de evaluaciones | ✅ | la muestra está sesgada al alza por `PERF-04` |
| 3 — Garbage collector del caché | ✅ | requiere limpiar antes las filas de `BUG-01` |
| 4 — BM25 multilingüe | ✅ | correctamente identificado |
| 5 — GraphRAG topológico | ✅ | contradice la afirmación del README sobre NetworkX (`DOC-04`) |

---

## 12. Anexo B: Constantes y Umbrales del Sistema

Inventario de todos los valores numéricos que gobiernan el comportamiento, con su ubicación y estado de documentación.

| Constante | Valor | Ubicación | Documentado en | Estado |
|---|:---:|---|---|:---:|
| Dimensión del embedding | 384 | `sql/01_init.sql:7` + 4 servicios | `PAPER.md` §5.3 | ✅ |
| Modelo de embedding | `all-MiniLM-L6-v2` | 4 archivos | `README.md`, `PAPER.md` | ✅ |
| Modelo de reranking | `ms-marco-MiniLM-L-12-v2` | `reranker.py:10` | `PAPER.md` §9.2 | ✅ (`ARCHITECTURE.md` ❌) |
| Caché del re-ranker | `/tmp/flashrank` | `reranker.py:10` | — | ❌ `BUG-08` |
| Modelo LLM | `claude-haiku-4-5-20251001` | 7 llamadas | `README.md` dice 3.5 | ❌ `DOC-07` |
| Constante RRF $k$ | 60 | `retriever.py:54` | `PAPER.md` §5.1 | ✅ |
| Diccionario FTS | `'spanish'` | `retriever.py:44,46,47`, `01_init.sql:9` | `PAPER.md` §10.1 | ✅ (limitación reconocida) |
| `top_k` de retrieval | 15 | `nodes.py:70` (hardcodeado) | `PAPER.md` §5.1 | ⚠️ `BUG-06` |
| `top_k` de reranking | 10 | `nodes.py:83` (hardcodeado) | contrato dice 7 | ❌ `BUG-06` |
| Multiplicador de ruptura $c$ | 1.25 | `ingestion.py:78` | `PAPER.md` §5.2 | ✅ |
| `max_tokens` de chunk | 400 | `ingestion.py:48` | paper dice 500 | ❌ `DOC-06` |
| `overlap` de chunk | 0 (muerto) | `ingestion.py:48` | — | ❌ `DOC-06` |
| Umbral de caché | 0.85 | `cache.py:16` | `FASE_4_IMPL` §1, `PAPER.md` §5.3 | ✅ |
| TTL de caché | — (ninguno) | — | `ROADMAP` §3 | ✅ (pendiente reconocido) |
| Umbral de memoria | 0.3 | `memory.py:89` | `FASE_4_IMPL` §2 | ✅ |
| Top-K de memoria | 3 | `memory.py:66` | `FASE_4_IMPL` §2 | ✅ |
| Máx. hechos por extracción | 3 | `memory.py:19` (prompt) | `PAPER_PLAN` §2 | ✅ |
| Límite de aristas del grafo | 10 | `graphrag.py:86` | `PAPER.md` §5.5 | ✅ |
| Longitud mín. de nodo semilla | > 3 caracteres | `graphrag.py:72` | `PAPER.md` §5.5 | ✅ |
| Límite de iteraciones | 2 | `graph.py:13` | `PAPER.md` §5.4 | ⚠️ `BUG-05` |
| Ventana de historial | 4 mensajes | `router.py:41` | — | ⚠️ inalcanzable (`BUG-03`) |
| Expiración del JWT | 60 min | `auth.py:10` | — | ✅ |
| HNSW `m` / `ef_construction` | 16 / 64 | defaults de pgvector | `PAPER.md` §5.3 | ✅ |
| Timeout de herramientas | 5 s | `tools.py:16,32` | `PAPER_PLAN` §2 | ✅ |
| Puerto de Postgres | 5433 → 5432 | `docker-compose.yml:8` | `README.md` | ✅ |

---

## 13. Anexo C: Inventario de Llamadas al LLM

Siete invocaciones, todas vía `instructor.from_anthropic(AsyncAnthropic(...))` salvo la de visión.

| # | Función | Archivo:línea | `response_model` | `max_tokens` | Momento | Observaciones |
|:---:|---|---|---|:---:|---|---|
| 1 | `analyze_query` | `router.py:74` | `QueryIntent` | 500 | Síncrono (supervisor) | Historial siempre vacío (`BUG-03`) |
| 2 | `generate_answer` | `extractor.py:41` | `StructuredAnswer` | 8192 | Síncrono (generador) | Tras `DOC-01`, solo como repliegue |
| 3 | `generate_answer_stream` | `extractor.py:76` | `Partial[StructuredAnswer]` | 8192 | **Nunca** | Código muerto (`DOC-01`) — corregido: hoy es el camino normal del redactor |
| 4 | `extract_and_save_facts` | `memory.py:36` | `ExtractedFacts` | 200 | Background | Excepciones absorbidas |
| 5 | `extract_knowledge_graph` | `graphrag.py:35` | `KnowledgeGraphExtraction` | 1024 | Ingestión (por chunk) | Excepciones absorbidas |
| 6 | `evaluate_rag_response` | `evaluator.py:58` | `RAGEvaluation` | 300 | Background | `PERF-04`, `DOC-02` |
| 7 | `describe_image_with_claude` | `ingestion.py:117` | — (texto plano) | 1000 | Ingestión (por imagen) | Única sin Instructor; cliente instanciado por llamada |

**Observaciones transversales.**

- **Ninguna llamada fija `temperature`**, por lo que todas usan el default del modelo (1.0). Para tareas de clasificación (#1), extracción estructurada (#4, #5) y evaluación (#6), una temperatura baja (0.0–0.2) daría resultados más estables y reproducibles. `PAPER_PLAN.md` §3.4 lo documenta como decisión, pero no justifica por qué es la adecuada para tareas deterministas.
- **`describe_image_with_claude` instancia un `AsyncAnthropic` nuevo en cada invocación** (`ingestion.py:113`), a diferencia de los otros seis que reutilizan un cliente a nivel de módulo. En un PDF con 20 imágenes son 20 clientes creados y descartados.
- **Coste por consulta compleja:** 3 llamadas al LLM en el camino normal (router + generador + evaluador) más 1 de memoria en background = **4**. Con el ciclo de `BUG-05`: **5**.

---

## 14. Anexo D: Inventario de Prompts del Sistema

Los seis prompts que gobiernan el comportamiento, con su ubicación exacta para revisión.

| Agente | Ubicación | Rol | Longitud aprox. |
|---|---|---|:---:|
| **Router / Supervisor** | `router.py:48-70` | Clasifica en 4 intenciones; genera 3 variantes Multi-Query y 1 documento HyDE | 23 líneas |
| **Generador** | `extractor.py:26-37` | Responde solo con el contexto; cita por ID; marca `requires_more_info` | 12 líneas |
| **Generador (stream)** | `extractor.py:64-73` | Igual + instrucción anti-texto-plano de `TROUBLESHOOTING.md` §6 | 10 líneas |
| **Extractor de grafos** | `graphrag.py:26-33` | Extrae tripletas (origen, relación, destino) | 8 líneas |
| **Extractor de memoria** | `memory.py:28-33` | Extrae hechos persistentes en tercera persona, máx. 3 | 6 líneas |
| **Evaluador** | `evaluator.py:40-55` | Juez imparcial; 3 métricas de 0.0 a 1.0 + razonamiento | 16 líneas |
| **Descriptor de imágenes** | `ingestion.py:115` | Describe imagen en detalle para RAG; extrae texto visible | 1 línea |

**Observaciones.**

- El prompt del router (`router.py:49`) codifica el dominio como constante: *"un AI Engineer Sandbox que actualmente está analizando el currículum y perfil profesional del ingeniero Bryan Bobadilla"*. Es la solución documentada en `TROUBLESHOOTING.md` §1 y funciona, pero acopla el sistema a un caso de uso concreto: cualquier tenant que ingiera otro tipo de documento recibe un router sesgado hacia un CV que no es el suyo. En un sistema multi-tenant real, ese contexto debería derivarse del corpus del tenant.
- El prompt del generador (`extractor.py:26-37`) **no incluye** la instrucción anti-texto-plano que sí tiene la versión de streaming (`extractor.py:67`), pese a que `TROUBLESHOOTING.md` §6 documenta ese fallo como genérico de Haiku ante peticiones de análisis largo. Como la versión de streaming está muerta (`DOC-01`), **la instrucción que resolvió el bug no se aplica en el único camino activo**. Es un hallazgo derivado de `DOC-01` que conviene corregir junto a él. **Corregido (2026-09-13):** los dos redactores comparten ahora `_build_prompt()`, así que la instrucción se aplica en ambos y no puede volver a divergir.
- Todos los prompts van en el turno `user`; ninguno usa el parámetro `system` de la API de Anthropic, que es el lugar canónico para instrucciones de rol y habilita el caching de prompt cuando el contenido es estable. Para el router y el evaluador —cuyas instrucciones son idénticas en cada invocación— sería una optimización directa de coste y latencia.

---

## 15. Anexo E: Comandos de Verificación

Reproducción completa de los hallazgos sin ejecutar el sistema.

```bash
# --- Seguridad ---
grep -n "SECRET_KEY\|password123" src/api/auth.py            # SEC-01
grep -n "tenant_id: str" src/api/auth.py                      # SEC-02
grep -rn "SET app.current_tenant" src/ | wc -l                # SEC-02 → 9
sed -n '69,89p' src/services/graphrag.py                      # SEC-03
sed -n '20,27p' src/api/routers/ingest.py                     # SEC-04

# --- Defectos funcionales ---
sed -n '112,124p' src/api/routers/chat.py                     # BUG-01
grep -n "intent_type" src/api/routers/chat.py                 # BUG-02 → ninguna
grep -rn "history" src/ | grep -v "^src/frontend"             # BUG-03
ls sql/ | sort && grep -n "app_user" sql/*.sql                # BUG-04
grep -c "knowledge_graph\|FORCE" sql/01_init.sql              # BUG-04 → 0
sed -n '11,18p' src/services/agent_graph/graph.py             # BUG-05
grep -rn "top_k_retrieve\|top_k_rerank" src/                  # BUG-06 → solo la definición
grep -n "retrieve_documents(query" tests/test_rag.py          # BUG-07
sed -n '76,83p' .venv/lib/*/site-packages/flashrank/Ranker.py  # BUG-08 (chequeo por directorio)
ls -la /tmp/flashrank/*/                                      # BUG-08 (directorios vacíos)

# --- Rendimiento ---
grep -rn "create_pool" src/                                   # PERF-01 → ninguna
grep -rn "asyncpg.connect" src/ | wc -l                       # PERF-01 → 9
grep -rn "SentenceTransformer(" src/                          # PERF-02 → 4
grep -n "model.encode" src/services/ingestion.py              # PERF-03
grep -n "max_tokens" src/services/*.py                        # PERF-04

# --- Divergencias documentales ---
grep -rn "generate_answer_stream" src/                        # DOC-01 → solo la definición
grep -n "ge=\|le=" src/services/evaluator.py                  # DOC-02 → ninguna
cat .env.example && grep -rn "OPENAI" src/                    # DOC-03
grep -rn "networkx" src/ pyproject.toml                       # DOC-04 → ninguna
grep -n "max_tokens\|overlap" src/services/ingestion.py       # DOC-06
grep -rn "claude-haiku" src/ | wc -l                          # DOC-07 → 7
grep -n "requires-python" pyproject.toml                      # DOC-08

# --- Higiene ---
grep -iE "jwt|numpy|multipart" pyproject.toml                 # HYG-01 → ninguna
ls *.py                                                       # HYG-02 → 6 scripts
git ls-files | grep -E "\.idea|\.log"                         # HYG-03
grep -n "utcnow" src/api/auth.py                              # HYG-04
```

---

## 16. Nota final

Los 28 hallazgos se concentran en tres causas raíz, y merece la pena nombrarlas porque explican el patrón mejor que la lista:

1. **La migración a LangGraph (Fase 4) fue quirúrgica en el código y no se propagó a la documentación.** El grafo funciona; lo que quedó atrás son las piezas del pipeline anterior que nadie desconectó (`DOC-01`, `BUG-03`, `BUG-06`) y los documentos que describían el flujo sustituido (`DOC-05`, partes de `TROUBLESHOOTING.md`).

2. **El entorno de desarrollo nunca se reprodujo desde cero.** `BUG-04`, `BUG-08`, `DOC-03` y parte de `HYG-01` derivan de que se construyó incrementalmente a mano: los scripts SQL se ejecutaron en orden lógico sobre una base ya existente, y el caché del re-ranker se descargó una vez en un directorio volátil. Ese estado es funcional en la máquina del autor y frágil o inexistente en cualquier otra.

3. **Los papers se escribieron describiendo el sistema deseado, no el ejecutado.** `DOC-02` y la afirmación del pool en `PERF-01` son las dos más claras. La formalización matemática es rigurosa y en su mayor parte fiel; las divergencias aparecen en las afirmaciones sobre implementación.

Ninguna de las tres cuestiona el diseño. El sistema, una vez aplicados los bloques 1 a 3, hace lo que la documentación dice que hace — y lo que la documentación dice es genuinamente avanzado.
