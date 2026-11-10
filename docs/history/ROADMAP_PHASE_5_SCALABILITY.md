# 🗺️ Phase 5 roadmap: scaling and DevOps (future work)

This document describes the 5 strategic initiatives (epics) identified at the end of Phase 4 to take the system from a "sandbox" to a fully scalable and observable cloud-native architecture.

---

### 1. 🐳 Full containerization (DevOps & deploy)
Currently, orchestration depends on the host having Python installed locally, limiting the use of Docker to the PostgreSQL layer.
- **Goal:** package the whole application for *serverless* deployments (e.g. Google Cloud Run, AWS ECS).
- **Technical tasks:**
  - Create an optimized `Dockerfile` (multi-stage build) using `uv` to minimize image size and build times.
  - Update `docker-compose.yml` to start the database, the backend (FastAPI) and the frontend (Streamlit) on the same virtual network.
  - Configure environment variables and *healthchecks*.

### 2. 📊 Evaluation analytics dashboard (data viz)
The passive agent (LLM-as-a-judge) constantly evaluates the system, but the data sits hidden in the database without being exploited visually.
- **Goal:** provide an observability window to detect model degradation.
- **Technical tasks:**
  - Create a new Streamlit tab/page (`Dashboard.py`).
  - Build FastAPI endpoints to query aggregated metrics.
  - Use libraries such as `altair` or `plotly` to render time series showing how *Faithfulness*, *Relevance* and *Context Precision* evolve.

### 3. 🧹 Garbage collector for the semantic cache (eviction policy)
The semantic cache (`semantic_cache`) inserts queries forever, which will eventually saturate RAM and degrade the retrieval speed of the HNSW index.
- **Goal:** implement an eviction policy (time-to-live).
- **Technical tasks:**
  - Create a periodic task (cron job) in FastAPI using `APScheduler` or `asyncio`.
  - Design an asynchronous SQL query that sweeps (`DELETE`) the rows whose `created_at` field exceeds a configured threshold (e.g. 7 days).

### 4. 🌐 Dynamic multilingual lexical search (BM25)
PostgreSQL's native *full-text search* configuration currently uses a hard coercion: `to_tsvector('spanish', content)`. If documents in other languages are ingested, *stemming* and *stop words* will fail catastrophically.
- **Goal:** make the database respect the original language of each chunk.
- **Technical tasks:**
  - Integrate a language detection library (such as `langdetect` or `lingua-py`) into the ingestion pipeline (`src/services/ingestion.py`).
  - Change the SQL schema to accept the language as a column and generate the vector dynamically, or force the language to be injected as a parameter in the retriever's queries.

### 5. 🕸️ Advanced GraphRAG (topological graph theory)
The current GraphRAG implementation extracts nodes efficiently, but its retrieval uses a flat 1-hop regular expression, ignoring the real weight of community relations.
- **Goal:** give the model a mathematically central context subgraph.
- **Technical tasks:**
  - Implement the `NetworkX` library or migrate the data to a native graph engine such as `Neo4j` / `Apache Age`.
  - Compute *PageRank*, community detection (*Leiden*) or *betweenness centrality* algorithms over the stored triples before injecting them into the generator node's context.
