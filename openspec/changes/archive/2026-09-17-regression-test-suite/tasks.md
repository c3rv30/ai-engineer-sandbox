## 1. Configuración de pytest y dependencias

- [x] 1.1 En `pyproject.toml`, sacar `pytest` de `dependencies` y crear `[dependency-groups] dev` con `pytest` y `pytest-asyncio`, con `uv remove`/`uv add --dev` y `--no-sync` (nunca `uv sync`: desinstalaría `pyjwt`, que no está declarado, `HYG-01`); verificar que `uv run pytest --version` responde y que el `.venv` conserva `pyjwt`
- [x] 1.2 Añadir `[tool.pytest.ini_options]` con `testpaths = ["tests"]`, los marcadores `db` y `eval`, `--strict-markers` y el `loop_scope` de pytest-asyncio (design D9); verificar que `uv run pytest --collect-only` no recoge ningún `test_*.py` de la raíz
- [x] 1.3 Crear `tests/unit/`, `tests/db/` y `tests/evals/`, mover `tests/test_rag.py` a `tests/evals/` y excluirlo de la recolección salvo con `--run-evals` (D9); verificar que `uv run pytest --collect-only` no importa `deepeval` y que `--run-evals` sí lo recoge
- [x] 1.4 Crear `tests/conftest.py`, que fija `DATABASE_URL` (puerto 5439), `TENANT_SIGNING_KEY` y `JWT_SECRET_KEY` aleatorias y `DB_POOL_MIN_SIZE=1` antes de cualquier importación de `src` (D5); verificar con un test temporal que `src.services.db.DB_DSN` apunta al 5439 aunque exista el `.env` de desarrollo

## 2. Capa 1 contra el código actual

- [x] 2.1 Escribir en `tests/unit/` los tests de la política de caché (spec: *Regresión de la política de caché*), importando de `src.api.routers.chat`; verificar que pasan
- [x] 2.2 Escribir los tests de la ventana de recuperación y de `route_reviewer` (spec: *Regresión del ciclo de auto-corrección*, salvo *Corpus agotado* y *Ventana saturada*, que dependen de la extracción de 3.3), importando de `nodes.py` y `graph.py`; verificar que pasan
- [x] 2.3 Escribir los tests de `format_history` (spec: *Regresión del historial de conversación*); verificar que pasan
- [x] 2.4 Escribir el test de límites de `RAGEvaluation` (spec: *Regresión de los límites de las puntuaciones del evaluador*), importando de `src.services.evaluator`; verificar que pasa
- [x] 2.5 Escribir el test de `sign_tenant` contra un HMAC-SHA256 calculado en el propio test con la biblioteca estándar; verificar que pasa (la comparación con el HMAC de la base se hace en 6.1)

## 3. Extracciones sin cambio de comportamiento

- [x] 3.1 Mover la política de caché a `src/services/cache_policy.py` y hacer que `chat.py` la importe de ahí (D2); verificar que los tests de 2.1, apuntando al módulo nuevo, dan los mismos resultados y que `from src.api.routers.chat import is_cache_eligible` sigue funcionando
- [x] 3.2 Mover `retrieval_window`, `route_supervisor` y `route_reviewer` a `src/services/agent_graph/routing.py`, importados desde `nodes.py` y `graph.py`; verificar que los tests de 2.2, apuntando al módulo nuevo, dan los mismos resultados
- [x] 3.3 Extraer a `routing.py` la decisión de agotamiento que hoy está en línea en `researcher_node`, como función con las mismas entradas (tamaños de resultados, candidatos únicos, ventana actual y base), y usarla desde `researcher_node`; escribir los escenarios *Corpus agotado* y *Ventana saturada* y verificar que pasan
- [x] 3.4 Extraer el saneado del nombre de origen a `src/services/filenames.py` y usarlo desde `ingest_endpoint`; escribir los tests de *Regresión del nombre de archivo en la ingesta* (con `/`, `\` y `..`) y verificar que pasan
- [x] 3.5 Mover `RAGEvaluation` a `src/models/evaluation.py`, importado desde `evaluator.py`; verificar que el test de 2.4, apuntando al módulo nuevo, pasa
- [x] 3.6 Arrancar la API real contra la base de desarrollo, hacer una pregunta de conocimiento con historial y otra sin él, y comprobar que responden y que el caché se usa solo en la segunda; verificar además que la base de desarrollo queda con los recuentos iniciales (purgando lo que escriban la petición y sus tareas en segundo plano)

## 4. Pureza de la capa 1

- [x] 4.1 Escribir el test guardián (D3): importa en un subproceso limpio todos los módulos que usa `tests/unit/` y comprueba que `sys.modules` no contiene `sentence_transformers`, `flashrank`, `anthropic` ni `langgraph`; verificar que pasa y que falla si se añade `import src.services.agent_graph.nodes` a la lista
- [x] 4.2 Ejecutar `uv run pytest tests/unit` en un clon limpio, sin `.env` y con Docker parado; verificar que todo pasa en segundos (spec: *Clon sin configuración* y *Selección explícita de la capa pura*)

## 5. Base desechable

- [x] 5.1 Escribir en `tests/db/conftest.py` el fixture de sesión con el ciclo de D4 (limpieza previa por nombre exacto, `up --wait`, `pytest.fail` si falla, `down` y borrado del volumen en el finalizador) y el marcado automático como `db`; verificar que tras una ejecución no quedan ni contenedor ni volumen `sandbox_tests*`
- [x] 5.2 Añadir el guardián del DSN (D5) al fixture; verificar que aborta la sesión si `DB_DSN` no apunta al 5439 (forzándolo en una prueba temporal)
- [x] 5.3 Configurar el event loop de sesión y el cierre del pool (D6); verificar con `pg_stat_activity` durante una ejecución que las conexiones de `app_user` no crecen con el número de tests
- [x] 5.4 Verificar la limpieza tras un fallo y tras una interrupción: con un test que falla a propósito y con un `kill -9` a mitad de ejecución, la ejecución siguiente arranca limpia y al terminar no queda nada
- [x] 5.5 Verificar el fallo sin Docker (spec: *Docker no disponible*): con Docker parado, `uv run pytest` termina con fallo, y el mensaje dice que no se pudo levantar la base de pruebas

## 6. Capa 2

- [x] 6.1 Escribir los tests de *Regresión del aislamiento entre tenants*: contexto firmado válido (con control positivo), sin firma, firma falsa y tenant reescrito desde la sentencia, a través de `tenant_connection`; completar el escenario *Firma coincidente* comparando `sign_tenant` con el HMAC calculado por la base; verificar que pasan
- [x] 6.2 Escribir el test de inyección en GraphRAG: sembrar relaciones en dos tenants y llamar a `retrieve_subgraph` con el payload de `SEC-03` desde el tenant sin ellas, con control positivo desde el dueño; añadir, con tokenizador permisivo, la tautología y el apóstrofo (escenario *Palabras de la pregunta como datos*, añadido al implementar: la lectura entre tenants ya la bloquea `SEC-05` y sola no detectaría la vuelta de `SEC-03`); verificar que pasan
- [x] 6.3 Escribir el test de la conexión reutilizada del pool (`PERF-01`), forzando que la segunda operación reciba la misma conexión física, y el de *Contexto local a la transacción* con un pool sin reset (añadido al implementar: el `RESET ALL` de asyncpg ocultaría un `set_config(..., false)`); verificar que pasan
- [x] 6.4 Escribir los tests de *Regresión de los privilegios del rol de la aplicación* (tabla nueva, `CREATE SCHEMA`, ajustes guardados del rol, clave de firma); verificar que pasan
- [x] 6.5 Verificar que la base de desarrollo no se toca: recuentos 22/128/4/3/0 y el mismo volumen `ai_engineer_sandbox_pgdata` antes y después de `uv run pytest` con la base de desarrollo en marcha

## 7. Control negativo por hallazgo

- [x] 7.1 Para cada hallazgo de capa 1 (`BUG-02`, `BUG-06`, `BUG-10`, `BUG-05`, `BUG-03`, `SEC-04`, `DOC-02`), reintroducir el comportamiento anterior (D8), comprobar que falla al menos un test de ese hallazgo y deshacer; anotar aquí qué test falló en cada caso
- [x] 7.2 Para cada hallazgo de capa 2 (`SEC-05`, `SEC-03`, `PERF-01`, `HYG-07`, `SEC-07`), reintroducir el SQL o el código anterior en la base desechable o en el código (D8), comprobar que falla al menos un test y deshacer; anotar aquí qué test falló en cada caso
- [x] 7.3 Comprobar el escenario *Base recién creada* (`BUG-04`) rompiendo temporalmente el orden de los scripts de `sql/`: la sesión debe terminar en `pytest.fail`; deshacer

### Resultados del control negativo (2026-09-16)

Cada mutación se aplicó sobre el código o `sql/`, se ejecutó la capa correspondiente y se restauró con `git checkout` (árbol limpio al terminar; 0 contenedores y 0 volúmenes de prueba tras cada ejecución).

| Hallazgo | Comportamiento reintroducido | Tests que fallan |
|---|---|---|
| `BUG-02` | cachear cualquier respuesta (antes de `d198be1`) | 10: intención no cacheable, confianza insuficiente o ausente, sin campo, pide más información |
| `BUG-02` | solo quitar la lista blanca de intenciones | 5: intención no cacheable |
| `BUG-06` | el caché ignora los `top_k` propios | 3: parámetros propios no usan caché |
| `BUG-06` | `top_k_retrieve` sin `ge`/`le` | 3: parámetros fuera de rango |
| `BUG-10` | el caché ignora el historial (antes de `82c7aa6`) | 1: petición con historial no usa caché |
| `BUG-05` | la ventana no se amplía (antes de `e8c63b6`) | 7, entre ellos ampliación por reintento y ventana saturada |
| `BUG-05` | el revisor ignora `retrieval_exhausted` | 1: no se reintenta si la búsqueda está agotada |
| `BUG-05` | nunca se considera agotada | 3: corpus agotado, sin variantes, ventana saturada |
| `BUG-05` | ampliación sin tope en los máximos | 6: tope en los máximos, se estanca, ventana saturada |
| `BUG-03` | el historial se descarta (defecto original) | 2: ventana de turnos, turnos malformados |
| `BUG-03` | sin ventana de turnos | 1: ventana de turnos |
| `BUG-03` | `msg["role"]` sin tolerar turnos malformados | 3: turnos malformados, historial inutilizable |
| `SEC-04` | nombre del cliente tal cual (antes de `4ea6449`) | 8: último componente, sin separadores |
| `SEC-04` | `basename` sin normalizar `\` | 2: último componente, sin separadores |
| `DOC-02` | puntuaciones sin `ge`/`le` (antes de `debf63c`) | 6: puntuación fuera de rango |
| `SEC-05` | políticas sobre `current_setting`, sin firma (antes de `38316a0`) | 5: sin firma, firma falsa, firma de otro tenant, tenant reescrito, base recién creada |
| `SEC-03` | `WHERE` por concatenación (antes de `6af7530`) | 2: tautología, apóstrofo. La lectura entre tenants **no** falla: la bloquea `SEC-05`, como se anticipó |
| `PERF-01` | `set_config(..., false)` en `tenant_connection` | 1: contexto local a la transacción. El test del pool real **no** falla: lo oculta el `RESET ALL`, como se anticipó |
| `HYG-07` | `ALTER DEFAULT PRIVILEGES` de vuelta (antes de `6216534`) | 1: tabla nueva en `public` |
| `SEC-07` | `GRANT ALL` sobre la base (antes de `c917833`) | 1: no puede crear esquemas |
| `SEC-07` | `ALTER ROLE app_user SET search_path` guardado | 1: sin ajustes propios guardados |
| `BUG-04` | `00_create_app_user.sql` renombrado a `02_` | la sesión termina con código 1: 18 errores, "No se pudo levantar la base de pruebas con docker compose" |

## 8. Cierre

- [x] 8.1 Ejecutar `uv run pytest` completo dos veces seguidas; verificar que las dos pasan y que no queda ni contenedor ni volumen de pruebas
- [x] 8.2 Añadir la línea de estado de `BUG-07` en `docs/AUDITORIA_TECNICA.md` (tabla de §1, ficha y plan §10), con la corrección de que el parche mínimo de la ficha ya no aplicaba, y con la tabla de controles negativos de 7.1 a 7.3; anotar en la ficha de `HYG-01` que `uv sync` desinstala hoy `pyjwt` y deja la API sin arrancar (comprobado con `--dry-run` el 2026-09-16)
- [x] 8.3 Hacer los commits con las mediciones en el cuerpo, siguiendo la práctica del proyecto; verificar con `git status` que no queda nada sin commitear fuera de lo decidido
