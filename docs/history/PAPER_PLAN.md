# Paper writing plan: AI Engineer Sandbox

## 1. Full file inventory

**Configuration, dependencies and infrastructure**
- `pyproject.toml` / `uv.lock`: dependency definitions and environment configuration (FastAPI, LangGraph, Anthropic, Instructor, PgVector, FlashRank).
- `docker-compose.yml`: starts the PostgreSQL 16 database with the `pgvector` extension. (Note: there is no `Dockerfile`; the official image is used directly.)
- `.env.example`: environment variable template (Anthropic API keys and the JWT secret).

**Database (SQL)**
- `sql/00_create_app_user.sql`: creates the `app_user` role the application connects with. It runs first.
- `sql/01_init.sql`: unified script that creates the tables (`documents`, `semantic_cache`, `user_memory`, `rag_evaluations`, `knowledge_graph`), enables and forces RLS, creates the HNSW indexes and grants privileges to `app_user`.
- `sql/migrations/` (`apply_cache.sql`, `apply_evaluator.sql`, `apply_graphrag.sql`, `apply_memory.sql`, `apply_rls.sql`): individual iterative migration scripts used during development on an existing database. The Docker bootstrap does not run them.

**Frontend & API (presentation layer)**
- `src/frontend/app.py`: Streamlit client. It consumes the backend's SSE (Server-Sent Events) to show real-time streaming.
- `src/api/main.py`: FastAPI entry point, middlewares (CORS) and initialization.
- `src/api/auth.py`: JWT authentication and the `get_current_user` dependency that extracts the `tenant_id`.
- `src/api/routers/chat.py`: inference endpoints (`/chat/` and `/chat/stream/`). It compiles and runs the StateGraph.
- `src/api/routers/ingest.py`: document upload endpoint.
- `src/api/routers/__init__.py`, `src/api/__init__.py`: package initialization modules.

**Core RAG and optimization services (logic layer)**
- `src/services/ingestion.py`: semantic chunking algorithm.
- `src/services/retriever.py`: hybrid vector + FTS search with RRF.
- `src/services/reranker.py`: cross-encoder model with FlashRank.
- `src/services/graphrag.py`: extraction and retrieval of semantic triples with LLMs.
- `src/services/cache.py`: query interception through the semantic cache (HNSW).
- `src/services/memory.py`: storage and retrieval of the user's long-term memory.
- `src/services/extractor.py`: final structured generation of the answer.
- `src/services/evaluator.py`: runs LLM-as-a-judge to evaluate RAG metrics.
- `src/services/router.py`: initial intent analysis, HyDE and Multi-Query.
- `src/services/tools.py`: registry and execution of external tools (function calling).

**Agentic orchestration (LangGraph)**
- `src/services/agent_graph/graph.py`: defines the graph, the routing conditionals and the assembly.
- `src/services/agent_graph/nodes.py`: implementation of the 3 main nodes.
- `src/services/agent_graph/state.py`: shared state (TypedDict) for the agents.
- `src/services/agent_graph/__init__.py`: package module.

**Contract models (Pydantic v2)**
- `src/models/structured.py`: `StructuredAnswer`, `IntentAnalysis`.
- `src/models/search.py`: `SearchResult`, `RerankedResult`.
- `src/models/requests.py`: API input schemas (e.g. `ChatRequest`).

**Testing and secondary scripts**
- `tests/test_rag.py`: obsolete Phase 1 evals with DeepEval.
- `src/pipeline.py`: monolithic test script (Phase 1).
- `test_chunk.py`, `test_db.py`, `test_sim.py`, `test_sse.py`, `scratch_db.py`, `scratch_stream.py`: the developer's iterative local validation scripts (dead code/experiments).

---

## 2. Reconciled inventory: nodes, agents and prompts

The system is a hybrid of hard-coded routines (nodes) and LLM calls (agents).

### StateGraph nodes (main flow)
1. **Node: Supervisor (`supervisor_node` in `nodes.py`)**
   - **LLM agent it calls:** `analyze_query` in `src/services/router.py`.
   - **System prompt:** "You are the 'Router' of an AI Engineer Sandbox... Decide the intent... Generate 3 variations of the question... Write a hypothetical_document...".
2. **Node: Researcher (`researcher_node` in `nodes.py`)**
   - **LLM agent it calls:** NONE. It runs concurrent Python calls to Postgres (`retriever.py`), FlashRank (`reranker.py`) and the graph table (`retrieve_subgraph`).
3. **Node: Generator (`generator_node` in `nodes.py`)**
   - **LLM agent it calls:** `generate_answer` in `src/services/extractor.py`.
   - **System prompt:** "You are an expert answering questions... Use [Doc X] to cite... Context about the user: {user_profile}...". The node conceptually acts as the *Reviewer* by checking the completeness flag.

### Asynchronous agents (background / ingestion)
4. **Graph extraction agent (`extract_knowledge_graph` in `src/services/graphrag.py`)**
   - **Prompt:** "You are a GraphRAG expert. Extract a knowledge graph from the following text... Return the results as triples (SOURCE NODE, RELATION, TARGET NODE)."
5. **Memory extraction agent (`extract_and_save_facts` in `src/services/memory.py`)**
   - **Prompt:** "You are an assistant that extracts useful 'facts' or preferences of the user... Write them in the third person, short sentences."
6. **Evaluator agent (`evaluate_rag_response` in `src/services/evaluator.py`)**
   - **Prompt:** "You are an impartial judge evaluating a RAG system. Your job is to score 3 metrics from 0.0 to 1.0... 1. Faithfulness... 2. Answer Relevance... 3. Context Precision..."

### Intent tools (implemented tools)
Defined in `src/services/tools.py` and run directly by the **Supervisor node**:
1. `get_current_time()`: returns the system's local time.
2. `get_crypto_price(symbol)`: HTTP request to CoinGecko. 5 s timeout.
3. `get_github_profile(username)`: HTTP request to the GitHub API. 5 s timeout.

---

## 3. Mathematics and quantitative logic

1. **Multi-Query fusion and deduplication (`src/services/agent_graph/nodes.py`)**
   - *Logic:* asynchronous execution of `retrieve_documents(q, tenant_id, top_k=...)` for the original query, the 3 Multi-Query variations and the HyDE document. The window is computed by `retrieval_window`: it starts from the `ChatRequest`'s `top_k_retrieve`/`top_k_rerank` (15/10 by default) and widens on each retry of the loop.
   - *Deduplication:* the concurrent lists are collapsed into one and duplicates are filtered with a Python `set()` comparing the exact `doc.content` property.
2. **Conditional routing logic (`src/services/agent_graph/graph.py`)**
   - *Supervisor to exit:* `route_supervisor` evaluates `if state.get("final_answer")` -> `END`. Otherwise, `researcher`.
   - *Self-correction loop:* the `route_reviewer` function decides the iteration. Its name comes from intercepting the result of the review (done by the generator) to route. 
   - *Condition:* `if state.get("needs_more_info") and state.get("iterations", 0) < 2` and `not state.get("retrieval_exhausted")` -> `researcher`. If the search can no longer be widened, `END`.
   - Validation mapping: the extractor returns `StructuredAnswer.requires_more_info`. The `generator_node` maps this flag to the state as `state["needs_more_info"]`.
   - Increment (`nodes.py`): `researcher_node` returns `{"iterations": state["iterations"] + 1, "retrieval_exhausted": ...}`. Loop iteration limit: 2. On the retry, `retrieval_window` widens the window (15/10 → 30/15 with the defaults).
3. **Long-term memory (`src/services/memory.py`)**
   - *Logic:* extracts the top 3 facts. Uses `ORDER BY fact_embedding <=> $1::vector LIMIT 3`.
   - *Isolation:* applied through RLS by setting `SET app.current_tenant`.
4. **Embedding model and LLMs**
   - Embeddings: `sentence-transformers/all-MiniLM-L6-v2`. Dimensions: `384`.
   - Temperature: every Anthropic call through Instructor uses the model's default (1.0).
5. **HNSW vector index (`sql/01_init.sql`)**
   - Cosine distance operator: `vector_cosine_ops`.
   - Implicit `pgvector` defaults: `m = 16`, `ef_construction = 64`.
6. **BM25 ranking function (`src/services/retriever.py`)**
   - `ts_rank(fts, websearch_to_tsquery('spanish', query))`. The base language for normalization and stemming is fixed ('spanish').
7. **Reciprocal Rank Fusion (RRF)**
   - *Smoothing constant K:* 60. `COALESCE(1.0 / (60 + v.rank), 0.0) + COALESCE(1.0 / (60 + f.rank), 0.0)`. (Lines 33-34 in `retriever.py`.)
8. **Cross-encoder re-ranking (`src/services/reranker.py`)**
   - Model: `ms-marco-MiniLM-L-12-v2`. Input top_k (RRF) -> output top_k=10.
9. **Semantic chunking (`src/services/ingestion.py`)**
   - Iterative cosine similarity: `1 - (np.dot(a, b) / (norm_a * norm_b))`.
   - Break criterion (line 26): distance > `np.mean(distances) + 1.25 * np.std(distances)` or the chunk's accumulated tokens exceed `max_tokens=500`.
10. **Semantic cache (`src/services/cache.py`)**
    - Hit condition: cosine distance > `0.85`.
    - RLS isolation per tenant. It has no TTL/scheduled expiry policy (records live forever in this version).
11. **GraphRAG retrieval algorithm (`src/services/graphrag.py`)**
    - Seed nodes: filtered by the `\w+` regex, `len(w) > 3`. Fuzzy search `ILIKE '%{word}%'`.
    - Hops: flat retrieval (1 direct hop to the triple), arbitrary limit of `LIMIT 10` edges (line 59).
12. **Strict score limits (`sql/01_init.sql` / `evaluator.py`)**
    - `CHECK (score >= 0.0 AND score <= 1.0)` for `faithfulness_score`, `relevance_score` and `context_precision_score`.

---

## 4. Paper outline

1. **Abstract**
2. **Introduction**
3. **Theoretical framework and related work**
4. **System architecture**
   - 4.1. Overview and tech stack
   - 4.2. Multi-tenant database and security (RLS)
   - 4.3. Presentation layer: Server-Sent Events (SSE)
5. **Mathematical formalization**
   - 5.1. Hybrid search and Reciprocal Rank Fusion (RRF)
   - 5.2. Text segmentation (semantic chunking) through statistical analysis
   - 5.3. Vector spaces, semantic cache and cosine distance
   - 5.4. Formalization of the StateGraph as a state machine
   - 5.5. Formal definition of the evaluator's metrics (RAGAS-style)
6. **Design and implementation**
   - 6.1. Ecosystem of agents and nodes (Supervisor, Researcher, Generator)
   - 6.2. Two-stage retrieval (cross-encoder re-ranking)
   - 6.3. GraphRAG subsystem and long-term memory
   - 6.4. Tool invocation (function calling)
   - 6.5. Strict deterministic contracts (Instructor + Pydantic v2)
7. **End-to-end execution flow**
8. **Evaluation**
9. **Design decisions and trade-offs**
10. **Limitations and future work**
11. **Conclusion**
12. **References**
13. **Appendices**
   - 13.1. Full system prompts
   - 13.2. Table schemas (SQL)
   - 13.3. Notation glossary
   - 13.4. Open questions

---

## 5. Gaps, inconsistencies and documented limitations

1. **Evaluation results and benchmarks:** the system stores scores (`rag_evaluations`), but lacks systematic latency/cost measurements.
2. **Dead code:** files such as `src/pipeline.py` or the `scratch_*.py` scripts are not part of the production engine. `tests/test_rag.py` is architecturally obsolete.
3. **Forced infrastructure decisions:** FlashRank's default model returned 404, which forced a patch using `ms-marco-MiniLM-L-12-v2` as the fallback.
4. **Partial dockerization:** there is a `docker-compose.yml` for the DB, but no `Dockerfile` to package FastAPI/Python.
5. **BM25 degradation:** full-text search (FTS) uses the hard-coded `'spanish'` dictionary, which badly degrades the BM25 engine for documents in other languages (English, Portuguese).
6. **Suboptimal GraphRAG:** graph retrieval is naive (no centrality or community propagation).
