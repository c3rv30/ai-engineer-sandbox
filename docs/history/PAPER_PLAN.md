# Plan de Redacción del Paper: AI Engineer Sandbox

## 1. Inventario Completo de Archivos

**Configuraciones, Dependencias e Infraestructura**
- `pyproject.toml` / `uv.lock`: Definición de dependencias y configuración del entorno (FastAPI, LangGraph, Anthropic, Instructor, PgVector, FlashRank).
- `docker-compose.yml`: Levanta la base de datos PostgreSQL 16 con la extensión `pgvector`. (Nota: No existe `Dockerfile`, se usa la imagen oficial directamente).
- `.env.example`: Plantilla de variables de entorno (API keys de Anthropic y JWT secret).

**Base de Datos (SQL)**
- `sql/00_create_app_user.sql`: Crea el rol `app_user` con el que conecta la aplicación. Se ejecuta primero.
- `sql/01_init.sql`: Script unificado para crear tablas (`documents`, `semantic_cache`, `user_memory`, `rag_evaluations`, `knowledge_graph`), habilitar y forzar RLS, crear índices HNSW y conceder permisos a `app_user`.
- `sql/migrations/` (`apply_cache.sql`, `apply_evaluator.sql`, `apply_graphrag.sql`, `apply_memory.sql`, `apply_rls.sql`): Scripts individuales de migración iterativa usados durante el desarrollo sobre una base ya existente. El arranque de Docker no los ejecuta.

**Frontend & API (Capa de Presentación)**
- `src/frontend/app.py`: Cliente Streamlit. Consume SSE (Server-Sent Events) del backend para mostrar streaming en tiempo real.
- `src/api/main.py`: Punto de entrada de FastAPI, middlewares (CORS) e inicialización.
- `src/api/auth.py`: Autenticación JWT y dependencia `get_current_user` para extraer el `tenant_id`.
- `src/api/routers/chat.py`: Endpoints de inferencia (`/chat/` y `/chat/stream/`). Compila y ejecuta el StateGraph.
- `src/api/routers/ingest.py`: Endpoint de carga de documentos.
- `src/api/routers/__init__.py`, `src/api/__init__.py`: Módulos de inicialización.

**Servicios Base del RAG y Optimización (Capa Lógica)**
- `src/services/ingestion.py`: Algoritmo de Semantic Chunking.
- `src/services/retriever.py`: Búsqueda Híbrida Vector + FTS con RRF.
- `src/services/reranker.py`: Modelo Cross-Encoder con FlashRank.
- `src/services/graphrag.py`: Extracción y recuperación de tripletas semánticas con LLMs.
- `src/services/cache.py`: Interceptación de consultas vía Semantic Cache (HNSW).
- `src/services/memory.py`: Almacenamiento y recuperación de memoria a largo plazo del usuario (Long-Term Memory).
- `src/services/extractor.py`: Generación final estructurada de la respuesta.
- `src/services/evaluator.py`: Ejecución de LLM-as-a-judge para evaluar métricas de RAG.
- `src/services/router.py`: Análisis inicial de intents, HyDE, y Multi-Query.
- `src/services/tools.py`: Registro y ejecución de herramientas externas (Function Calling).

**Orquestación Agentic (LangGraph)**
- `src/services/agent_graph/graph.py`: Define el grafo, condicionales de ruteo y ensamblaje.
- `src/services/agent_graph/nodes.py`: Implementación de los 3 nodos principales.
- `src/services/agent_graph/state.py`: Estado compartido (TypedDict) para los agentes.
- `src/services/agent_graph/__init__.py`: Módulo.

**Modelos de Contratos (Pydantic v2)**
- `src/models/structured.py`: `StructuredAnswer`, `IntentAnalysis`.
- `src/models/search.py`: `SearchResult`, `RerankedResult`.
- `src/models/requests.py`: Esquemas de entrada API (ej. `ChatRequest`).

**Testing y Scripts Secundarios**
- `tests/test_rag.py`: Evals obsoletos de Fase 1 con DeepEval.
- `src/pipeline.py`: Script de prueba monolítico (Fase 1).
- `test_chunk.py`, `test_db.py`, `test_sim.py`, `test_sse.py`, `scratch_db.py`, `scratch_stream.py`: Scripts iterativos de validación local del desarrollador (código muerto/experimentos).

---

## 2. Inventario Reconciliado: Nodos, Agentes y Prompts

El sistema es un híbrido entre rutinas de código duro (Nodos) y llamadas a LLMs (Agentes).

### Nodos del StateGraph (Flujo Principal)
1. **Nodo: Supervisor (`supervisor_node` en `nodes.py`)**
   - **Agente LLM que invoca:** `analyze_query` en `src/services/router.py`.
   - **Prompt de Sistema:** "Eres el 'Router' de un AI Engineer Sandbox... Determina la intención... Genera 3 variaciones de la pregunta... Redacta un hypothetical_document...".
2. **Nodo: Investigador (`researcher_node` en `nodes.py`)**
   - **Agente LLM que invoca:** NINGUNO. Ejecuta concurrencia en Python para llamar a Postgres (`retriever.py`), a FlashRank (`reranker.py`) y a la tabla de grafos (`retrieve_subgraph`).
3. **Nodo: Generador (`generator_node` en `nodes.py`)**
   - **Agente LLM que invoca:** `generate_answer` en `src/services/extractor.py`.
   - **Prompt de Sistema:** "Eres un experto respondiendo preguntas... Usa [Doc X] para citar... Contexto sobre el usuario: {user_profile}...". El Nodo actúa conceptualmente como *Reviewer* al validar el flag de completitud.

### Agentes Asíncronos (Background / Ingestión)
4. **Agente de Extracción de Grafos (`extract_knowledge_graph` en `src/services/graphrag.py`)**
   - **Prompt:** "Eres un experto en GraphRAG. Extrae un grafo de conocimiento del siguiente texto... Devuelve los resultados en formato de tripletas (NODO ORIGEN, RELACIÓN, NODO DESTINO)."
5. **Agente de Extracción de Memoria (`extract_and_save_facts` en `src/services/memory.py`)**
   - **Prompt:** "Eres un asistente que extrae 'hechos' (facts) útiles o preferencias del usuario... Escríbelos en tercera persona, oraciones cortas."
6. **Agente Evaluador (`evaluate_rag_response` en `src/services/evaluator.py`)**
   - **Prompt:** "Eres un juez imparcial evaluando un sistema RAG. Tu trabajo es evaluar 3 métricas de 0.0 a 1.0... 1. Faithfulness... 2. Answer Relevance... 3. Context Precision..."

### Intent Tools (Herramientas Implementadas)
Definidas en `src/services/tools.py` y ejecutadas directamente por el **Nodo Supervisor**:
1. `get_current_time()`: Devuelve la hora local del sistema.
2. `get_crypto_price(symbol)`: Petición HTTP a CoinGecko. Timeout 5s.
3. `get_github_profile(username)`: Petición HTTP a GitHub API. Timeout 5s.

---

## 3. Matemática y Lógica Cuantitativa

1. **Fusión Multi-Query y Deduplicación (`src/services/agent_graph/nodes.py`)**
   - *Lógica:* Ejecución asíncrona de `retrieve_documents(q, tenant_id, top_k=...)` para la query original, las 3 variaciones de Multi-Query y el documento HyDE. La ventana la calcula `retrieval_window`: parte de `top_k_retrieve`/`top_k_rerank` del `ChatRequest` (15/10 por defecto) y se amplía en cada reintento del ciclo.
   - *Deduplicación:* Se colapsan las listas concurrentes en una y se filtran duplicados utilizando un `set()` de Python comparando la propiedad `doc.content` exacta.
2. **Lógica de Ruteo Condicional (`src/services/agent_graph/graph.py`)**
   - *Supervisor a Salida:* `route_supervisor` evalúa `if state.get("final_answer")` -> `END`. Si no, `researcher`.
   - *Self-Correction Loop:* La función `route_reviewer` se encarga de decidir la iteración. Su nombre se debe a que intercepta el resultado de la revisión (hecha por el generador) para rutear. 
   - *Condición:* `if state.get("needs_more_info") and state.get("iterations", 0) < 2` y `not state.get("retrieval_exhausted")` -> `researcher`. Si la búsqueda ya no puede ampliarse, `END`.
   - Mapeo de validación: El extractor devuelve `StructuredAnswer.requires_more_info`. El nodo `generator_node` mapea este flag al estado como `state["needs_more_info"]`.
   - Incremento (`nodes.py`): El `researcher_node` devuelve `{"iterations": state["iterations"] + 1, "retrieval_exhausted": ...}`. Límite iteraciones cíclicas: 2. En el reintento, `retrieval_window` amplía la ventana (15/10 → 30/15 con los valores por defecto).
3. **Memoria a Largo Plazo (`src/services/memory.py`)**
   - *Lógica:* Extrae top 3 hechos. Usa `ORDER BY fact_embedding <=> $1::vector LIMIT 3`.
   - *Aislamiento:* Aplicado a través del RLS estableciendo `SET app.current_tenant`.
4. **Modelo de Embeddings y LLMs**
   - Embeddings: `sentence-transformers/all-MiniLM-L6-v2`. Dimensiones: `384`.
   - Temperatura: En todas las llamadas a Anthropic vía Instructor se utiliza el default del modelo (1.0).
5. **Índice Vectorial HNSW (`sql/01_init.sql`)**
   - Operador de distancia coseno: `vector_cosine_ops`.
   - Defaults implícitos de `pgvector`: `m = 16`, `ef_construction = 64`.
6. **Función de Ranking BM25 (`src/services/retriever.py`)**
   - `ts_rank(fts, websearch_to_tsquery('spanish', query))`. El lenguaje base de normalización y stemming está fijado ('spanish').
7. **Reciprocal Rank Fusion (RRF)**
   - *Constante de suavizado K:* 60. `COALESCE(1.0 / (60 + v.rank), 0.0) + COALESCE(1.0 / (60 + f.rank), 0.0)`. (Líneas 33-34 en `retriever.py`).
8. **Cross-Encoder Reranking (`src/services/reranker.py`)**
   - Modelo: `ms-marco-MiniLM-L-12-v2`. Top_k de entrada (RRF) -> Top_k=10 de salida.
9. **Semantic Chunking (`src/services/ingestion.py`)**
   - Similitud Coseno Iterativa: `1 - (np.dot(a, b) / (norm_a * norm_b))`.
   - Criterio de quiebre (Línea 26): Distancia > `np.mean(distances) + 1.25 * np.std(distances)` o acumulación de tokens del chunk excede `max_tokens=500`.
10. **Semantic Cache (`src/services/cache.py`)**
    - Hit condition: Distancia coseno > `0.85`.
    - Aislamiento RLS por Tenant. No posee política de TTL/expiración programada (los registros son perpetuos en esta versión).
11. **Algoritmo de Recuperación GraphRAG (`src/services/graphrag.py`)**
    - Nodos semilla: Filtrado por regex `\w+`, `len(w) > 3`. Búsqueda difusa `ILIKE '%{word}%'`.
    - Saltos (Hops): Recuperación plana (1 salto directo a la tripleta), límite arbitrario `LIMIT 10` aristas (Línea 59).
12. **Límites Estrictos de Puntuación (`sql/01_init.sql` / `evaluator.py`)**
    - `CHECK (score >= 0.0 AND score <= 1.0)` para `faithfulness_score`, `relevance_score` y `context_precision_score`.

---

## 4. Índice del Paper

1. **Abstract**
2. **Introducción**
3. **Marco teórico y trabajo relacionado**
4. **Arquitectura del sistema**
   - 4.1. Visión general y Stack Tecnológico
   - 4.2. Base de Datos Multi-Tenant y Seguridad (RLS)
   - 4.3. Capa de Presentación: Server-Sent Events (SSE)
5. **Formalización matemática**
   - 5.1. Búsqueda Híbrida y Reciprocal Rank Fusion (RRF)
   - 5.2. Segmentación Textual (Semantic Chunking) vía Análisis Estadístico
   - 5.3. Espacios Vectoriales, Caché Semántico y Distancia Coseno
   - 5.4. Formalización del StateGraph como máquina de estados
   - 5.5. Definición formal de las métricas del evaluador (RAGAS-style)
6. **Diseño e implementación**
   - 6.1. Ecosistema de Agentes y Nodos (Supervisor, Investigador, Generador)
   - 6.2. Two-Stage Retrieval (Cross-Encoder Reranking)
   - 6.3. Subsistema GraphRAG y Memoria a Largo Plazo
   - 6.4. Invocación de Herramientas (Function Calling)
   - 6.5. Contratos Deterministas Estrictos (Instructor + Pydantic v2)
7. **Flujo de ejecución end-to-end**
8. **Evaluación**
9. **Decisiones de diseño y trade-offs**
10. **Limitaciones y trabajo futuro**
11. **Conclusión**
12. **Referencias**
13. **Apéndices**
   - 13.1. Prompts del Sistema Completos
   - 13.2. Esquemas de Tablas (SQL)
   - 13.3. Glosario de Notación
   - 13.4. Preguntas abiertas

---

## 5. Faltantes, Inconsistencias y Limitaciones Documentadas

1. **Resultados de Evaluación y Benchmarks:** El sistema guarda puntuaciones (`rag_evaluations`), pero carece de mediciones sistémicas de latencia/costo.
2. **Código Muerto:** Archivos como `src/pipeline.py` o scripts `scratch_*.py` no forman parte del motor en producción. `tests/test_rag.py` está obsoleto arquitectónicamente.
3. **Decisiones Forzadas de Infraestructura:** El modelo por defecto de FlashRank arrojó 404 obligando a parchar el sistema usando `ms-marco-MiniLM-L-12-v2` como fallback.
4. **Dockerización Parcial:** Existe `docker-compose.yml` para la BD, pero no `Dockerfile` para empaquetar FastAPI/Python.
5. **Degradación de BM25:** El texto Full-Text (FTS) utiliza el diccionario hardcodeado `'spanish'`, lo cual degrada agresivamente el motor BM25 para documentos ingresados en idiomas diferentes (inglés, portugués).
6. **GraphRAG Sub-óptimo:** La recuperación del grafo es ingenua (sin centralidad ni propagación comunitaria).
