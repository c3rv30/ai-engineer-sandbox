# Project context: AI Engineer Sandbox

> **Historical document (Phase 1).** It describes the project's starting point, with OpenAI as the model provider. The current system uses Anthropic (Claude), LangGraph, GraphRAG, long-term memory and an asynchronous evaluator, and reads no OpenAI key. For the current stack and setup, see `README.md` and `.env.example`.

## Goal
Implement a production-grade AI Engineering pipeline that covers:
1. Structured outputs & validation with `Instructor` + `Pydantic v2`.
2. Tracing and observability with `Langfuse`.
3. Storage and hybrid search (BM25/FTS + HNSW vector) in PostgreSQL with `pgvector` and RRF fusion.
4. Two-stage retrieval with a local cross-encoder (`flashrank`).
5. Non-deterministic testing and evals with `DeepEval`/`pytest`.

## Tech stack
- Runtime: Python 3.12 managed with `uv`.
- Clients & models: OpenAI (`gpt-4o-mini`, `text-embedding-3-small`), `Instructor`.
- DB: PostgreSQL 16 (`pgvector/pgvector:pg16`), `asyncpg`.
- Re-ranker: `flashrank` (ONNX on CPU).
- Observability: `langfuse`.

## Current status
- Modular architecture defined in `src/`:
  - `src/models/`: Pydantic contracts (`structured.py`, `search.py`).
  - `src/services/`: decoupled clients (`extractor.py`, `retriever.py`, `reranker.py`).
  - `sql/01_init.sql`: Postgres DDL with the `documents` table, GIN and HNSW indexes.
  - `docker-compose.yml`: Postgres service ready.

## Coding rules
- All code must be asynchronous where there is I/O (`asyncpg`, `AsyncOpenAI`).
- Strict typing with Pydantic on every interface.
- Instrument key functions with Langfuse's `@observe`.
- Zero unnecessary heavy dependencies (use `flashrank` instead of `torch`).
