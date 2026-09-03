# Contexto del Proyecto: AI Engineer Sandbox

## Objetivo
Implementar un pipeline de AI Engineering de nivel producción que cubre:
1. Structured Outputs & Validation con `Instructor` + `Pydantic v2`.
2. Tracing y Observabilidad con `Langfuse`.
3. Almacenamiento y Hybrid Search (BM25/FTS + HNSW Vector) en PostgreSQL con `pgvector` y fusión RRF.
4. Two-Stage Retrieval con Cross-Encoder local (`flashrank`).
5. Testing no determinista y Evals con `DeepEval`/`pytest`.

## Stack Técnico
- Runtime: Python 3.12 gestionado con `uv`.
- Clientes & Modelos: OpenAI (`gpt-4o-mini`, `text-embedding-3-small`), `Instructor`.
- DB: PostgreSQL 16 (`pgvector/pgvector:pg16`), `asyncpg`.
- Re-ranker: `flashrank` (ONNX en CPU).
- Observabilidad: `langfuse`.

## Estado Actual
- Arquitectura modular definida en `src/`:
  - `src/models/`: Contratos Pydantic (`structured.py`, `search.py`).
  - `src/services/`: Clientes desacoplados (`extractor.py`, `retriever.py`, `reranker.py`).
  - `sql/01_init.sql`: DDL de Postgres con tabla `documents`, índices GIN y HNSW.
  - `docker-compose.yml`: Servicio Postgres listo.

## Reglas de Codificación
- Todo el código debe ser asíncrono donde aplique I/O (`asyncpg`, `AsyncOpenAI`).
- Tipado estricto con Pydantic en todas las interfaces.
- Instrumentar funciones clave con `@observe` de Langfuse.
- Cero dependencias pesadas innecesarias (usar `flashrank` en lugar de `torch`).
