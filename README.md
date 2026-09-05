# 🚀 AI Engineer Sandbox: Enterprise Multi-Agent System

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20PgVector-336791.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-Agentic%20Orchestration-orange.svg)
![Anthropic](https://img.shields.io/badge/LLM-Claude%20Haiku-purple.svg)

Un motor avanzado de **Inteligencia Artificial y Sistemas RAG (Retrieval-Augmented Generation)** construido con estándares Enterprise. Este repositorio es un _showcase_ arquitectónico que demuestra la evolución desde un pipeline lineal simple de preguntas y respuestas, hasta un **Ecosistema Multi-Agente Autónomo** completamente orquestado con LangGraph.

Este proyecto aplica principios estrictos de **Clean Architecture**, asincronismo y validación determinista, garantizando un código de grado de producción escalable, seguro (Multi-Tenant) y con un alto nivel de observabilidad.

---

## 🧠 Arquitectura y Flujo Multi-Agente

En lugar de un router monolítico, la lógica de razonamiento está distribuida en un `StateGraph` cíclico con roles especializados:

```mermaid
graph TD
    User([👤 Usuario]) -->|Query| Supervisor[🤖 Nodo Supervisor]
    
    Supervisor -->|Evalúa Intent & HyDE| Router{¿Requiere Búsqueda?}
    Router -->|No (Charla, Herramientas)| END([Fin])
    Router -->|Sí| Researcher[🔍 Nodo Investigador]
    
    Researcher -->|Vector Search + GraphRAG| Reranker(⚡ FlashRank Re-ranker)
    Reranker --> Generator[✍️ Nodo Redactor]
    
    Generator -->|Analiza Completitud| Evaluator{¿Falta Información?}
    Evaluator -->|Sí (Falta Contexto)| Researcher
    Evaluator -->|No (Respuesta Lista)| FinalAnswer[💬 Respuesta al Usuario]
    FinalAnswer --> Background[⚙️ Tareas Background]
    
    Background --> LTM(🧠 Extraer Memoria a Largo Plazo)
    Background --> RAGEval(📊 RAG Evaluator / LLM-as-a-judge)
    Background --> Cache(💾 Guardar Caché Semántico)
```

---

## 🌟 Características Principales (SOTA)

### 1. 🤖 Orquestación Agentic (LangGraph)
*   **Routing Inteligente:** El flujo es gestionado por Nodos (Supervisor, Investigador, Revisor) que se comunican escribiendo en un Estado Global (`AgentState`).
*   **Ciclos de Razonamiento:** Si el Agente Redactor detecta que el contexto recuperado es insuficiente, rechaza la generación y devuelve el control al Investigador para hacer consultas más profundas.
*   **Herramientas Externas (Function Calling):** El supervisor puede desviar la consulta para invocar APIs externas de forma determinista.

### 2. 🔍 RAG Avanzado y Recuperación Multidimensional
*   **Semantic Chunking:** En lugar de dividir el texto arbitrariamente por cantidad de tokens, se utilizan algoritmos matemáticos (similitud coseno iterativa) para cortar los chunks respetando cambios radicales de tema.
*   **Two-Stage Retrieval (RRF + Cross-Encoder):** 
    1. *Retrieval Híbrido:* Fusión de Búsqueda Vectorial (`pgvector`) y Full-Text Search (BM25).
    2. *Reranking:* Re-ordenamiento ultra-rápido en CPU usando un modelo Cross-Encoder local (`FlashRank` / `ms-marco`).
*   **GraphRAG (Grafos de Conocimiento):** Extracción dinámica de entidades y relaciones (NetworkX) guardadas en Postgres. Al consultar, se recuperan sub-grafos para entender el panorama general.
*   **HyDE & Multi-Query:** Transformación de la consulta original por parte del Supervisor para mitigar la ambigüedad antes de tocar la base de datos.

### 3. 🛡️ Seguridad, Rendimiento y Producción
*   **Streaming SSE + Pydantic v2:** Generación estructurada de respuestas parciales en tiempo real a través de Server-Sent Events usando la librería `Instructor`. Garantiza JSON determinista sin alucinaciones de sintaxis.
*   **Multi-Tenancy por Base de Datos (RLS):** Autenticación mediante JWT. Total aislamiento de datos de clientes aplicando Políticas de Seguridad a Nivel de Fila (Row-Level Security) nativas en PostgreSQL.
*   **Caché Semántico:** Interceptación de preguntas repetidas. Si el *cos_distance* de la pregunta actual vs el historial es menor a 0.15, devuelve la respuesta cacheada sin consumir tokens de LLM (0% de latencia y costo).

### 4. 📊 Observabilidad Activa (LLM-as-a-judge)
*   Integración pasiva (Fire-and-forget Background Tasks) de un modelo de evaluación.
*   Cada respuesta generada es evaluada asíncronamente en 3 dimensiones: **Faithfulness** (Fidelidad/Alucinaciones), **Answer Relevance** y **Context Precision**. Todo queda persistido en BD.
*   Trazabilidad de inferencias en vivo usando **Langfuse** (`@observe`).

---

## 🛠️ Stack Tecnológico

*   **Backend Framework:** `FastAPI` (Python 3.12+, asíncrono puro).
*   **Agent Framework:** `LangGraph` + `LangChain Core`.
*   **LLM & Structured Outputs:** `Anthropic Claude 3.5 Haiku` + `Instructor` + `Pydantic v2`.
*   **Base de Datos y Vectores:** `PostgreSQL 16` + extensión `pgvector` + `asyncpg`.
*   **Embeddings & Reranker:** Modelos locales ultraligeros `sentence-transformers/all-MiniLM-L6-v2` y `FlashRank`.
*   **Frontend Interactivo:** `Streamlit` (para consumo de endpoints asíncronos en tiempo real).
*   **Gestor de Paquetes:** `uv`.

---

## 🚀 Cómo Ejecutar el Entorno Local

1. **Instalar el gestor ultrarrápido uv:**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   uv sync
   ```

2. **Levantar PostgreSQL con soporte PgVector:**
   ```bash
   docker compose up -d
   ```

3. **Configurar las Credenciales:**
   Copia el archivo `.env.example` a `.env` y añade tu `ANTHROPIC_API_KEY`.
   ```bash
   cp .env.example .env
   ```

4. **Arrancar el Backend y Frontend simultáneamente:**
   ```bash
   # Terminal 1: Inicia la API asíncrona
   PYTHONPATH=. uv run uvicorn src.api.main:app --port 8000 --reload
   
   # Terminal 2: Inicia la Interfaz Visual
   PYTHONPATH=. uv run streamlit run src/frontend/app.py
   ```
*(Opcional) Ingestar un documento base: `PYTHONPATH=. uv run python src/services/ingestion.py CONTEXT.md`*

---

## 📜 Histórico de Construcción (Roadmap)

Este Sandbox fue construido siguiendo una progresión meticulosa de 4 Fases para validar cada paradigma de la Ingeniería de IA:
1. **Fase 1 (Fundación):** RAG Básico en consola, Pydantic, PostgreSQL y Evals deterministas (DeepEval).
2. **Fase 2 (Evolución a Producto):** Clean Architecture, API REST (FastAPI), y parsing OCR multimodal con PyMuPDF.
3. **Fase 3 (SOTA Enterprise):** Autenticación Multi-Tenant (RLS), GraphRAG local, Streaming parcial (SSE) e inyección de Herramientas.
4. **Fase 4 (AI Systems Engineering):** Sistema Multi-Agente (LangGraph), Memoria Infinita a Largo Plazo, Semantic Chunking estadístico y Evaluaciones Asíncronas (LLM-as-a-judge).

---

> **Diseñado y desarrollado por Bryan.**
> *Demostrando experiencia comprobable en Arquitecturas Cloud y AI Engineering.*
