# Phase 4: Expert-level architectures (AI Systems Engineering)

Having completed phases 1 to 3, the AI Engineer Sandbox already has a very advanced **Enterprise RAG** pipeline (hybrid, re-ranking, multi-tenancy, GraphRAG, SSE streaming). 

To take the project to the highest level of AI engineering, we propose 6 possible lines of development, which turn a "good RAG" into a fully autonomous, observable, highly cost-efficient and contextually intelligent system.

---

## 1. RAG evaluator & active observability (RAGAS / TruLens)
Although the system currently uses Langfuse for call observability, the answers are not being evaluated mathematically at runtime.
- **Concept:** integrate an automated framework that assigns a score (0 to 1) to every generated answer on 4 critical dimensions:
  - **Context Precision:** were the relevant chunks placed first?
  - **Context Recall:** was information missing from the context to answer the question?
  - **Faithfulness:** does the answer hallucinate, or is everything backed by the context?
  - **Answer Relevance:** did the system answer the real question or drift away?
- **Suggested implementation:** use the `ragas` library and run a background worker (Celery or FastAPI BackgroundTasks) that evaluates every chat and sends it to the dashboard (Streamlit / Langfuse).

## 2. Multi-role agents (LangGraph / multi-agent)
The current system uses an "Agentic Router" that decides between running a tool, greeting or searching the RAG.
- **Concept:** move from a simple router to an orchestrated team of agents, where the flow is no longer linear. 
- **Proposed flow (state graph):**
  1. **Supervisor agent:** receives the question and breaks it down.
  2. **Researcher agent (web):** searches the internet if local context is missing.
  3. **RAG agent (local):** accesses Postgres and GraphRAG.
  4. **Reviewer agent (critic):** reviews the final draft. If it finds errors, it makes the RAG search better, creating an autonomous iteration loop (`Think -> Act -> Review`).
- **Suggested implementation:** `LangGraph` or the Antigravity SDK.

## 3. Semantic & hierarchical chunking (smart chunking)
The current chunking is based purely on a fixed mathematical size (256 tokens) using `tiktoken`.
- **Concept:** human text does not work by strict size, but by ideas (semantics).
- **Approaches:**
  - **Semantic chunking:** use embeddings to measure the exact point where a sentence changes topic, and cut the document there. It avoids breaking paragraphs in half.
  - **Hierarchical (parent-child) chunking:** split a document into large parts (pages = parents) and very small ones (sentences = children). We embed the children so the search is hyper-precise, but when we find a winning sentence, we inject the whole "page (parent)" into the LLM so it does not lack context.

## 4. Advanced query transformation (HyDE & Multi-Query)
RAG tends to fail if the question is very terse or uses different vocabulary from the document.
- **HyDE (Hypothetical Document Embeddings):** 
  - Before searching, the LLM "invents", or hallucinates, what it thinks the ideal document containing the answer would look like.
  - We embed that "hallucination" and search for it in the database. Mathematically, searching for an invented paragraph retrieves much more precise results than searching for a short question.
- **Multi-Query retrieval:**
  - The LLM receives the user's question and generates 3 variations of it. 
  - 3 concurrent asynchronous vector searches are run, and the results are merged and deduplicated. It completely removes failures due to synonyms or ambiguous wording.

## 5. Dynamic long-term memory (semantic memory profile)
Currently, the system remembers context by sending the full history of the current chat (stateful conversation memory). If the user clears the session, everything is lost.
- **Concept:** a persistent memory system at the "user profile" (tenant) level.
- **Implementation:**
  - A background agent reads every interaction and extracts *facts* ("Bryan likes Python", "Bryan uses macOS", "Company X works in healthcare").
  - These facts are embedded in a special index (e.g. `user_memory`).
  - When a new message arrives, the system silently injects that user's most relevant facts, achieving a hyper-personalization that spans sessions and days (similar to ChatGPT Plus's "Memory").

## 6. Semantic cache (cost & latency reduction)
With expensive LLM calls and search latency, answering identical questions is a waste of resources.
- **Concept:** implement a smart cache layer.
- **Implementation:**
  - Before entering the router or the RAG, we embed the user's question.
  - We search a Postgres `semantic_cache` table. If there is a previous question with cosine similarity `> 0.95`, we return the previous answer immediately.
  - The user gets instant answers (50 ms) and the inference cost drops to zero for frequent questions (FAQ).
