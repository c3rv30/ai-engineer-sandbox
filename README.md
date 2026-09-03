# AI Engineer Sandbox

Pipeline de AI Engineering con arquitectura modular diseñada para experimentación y uso de nivel producción. El objetivo de este proyecto es consolidar patrones avanzados de RAG (Retrieval-Augmented Generation), observabilidad, validación estructurada de datos y evaluación de Modelos de Lenguaje (LLMs).

## 🎯 Objetivos del Proyecto
1. **Structured Outputs & Validation:** Uso de `Instructor` y `Pydantic v2` para garantizar que las respuestas de los LLMs (Anthropic Claude) sigan esquemas estrictos de datos.
2. **Observabilidad:** Trazabilidad completa paso a paso utilizando `Langfuse` (`@observe`), midiendo latencia, costos y calidad de las inferencias.
3. **Almacenamiento Vectorial Local:** Base de datos PostgreSQL local enriquecida con la extensión `pgvector` para alojar embeddings de documentos.
4. **Two-Stage Retrieval (Recuperación en 2 Fases):** 
   - *Fase 1:* Búsqueda vectorial inicial mediante similitud coseno.
   - *Fase 2:* Re-ranking de los candidatos usando un modelo Cross-Encoder local de altísima precisión a través de `flashrank`.
5. **Testing No Determinista (Evals):** Evaluaciones continuas para métricas como relevancia, alucinación y context recall utilizando `DeepEval` y `pytest`.

---

## 🚀 Estado Actual (Fase 1: Completada)

El motor principal del sistema RAG ha sido implementado, testeado y se encuentra funcional con calidad de producción.

- [x] **Infraestructura y DB:** Proyecto gestionado con `uv` (Python 3.12+). PostgreSQL 16 con `pgvector`.
- [x] **Esquemas Estrictos (Pydantic v2):** Contratos de datos robustos en `src/models/`.
- [x] **Embeddings Locales:** `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dimensiones).
- [x] **Recuperación Híbrida RRF:** Fusión de Vector Search y Full-Text Search (BM25) en PostgreSQL.
- [x] **Cross-Encoder Reranking:** Uso de `flashrank` para re-ordenar candidatos.
- [x] **Generación Estructurada:** Uso de `instructor` y `claude-haiku-4-5-20251001` para generar JSON determinista con citas.
- [x] **Evaluaciones y Observabilidad:** `DeepEval` y `Langfuse`.

---

## 🗺️ Roadmap Fase 2: Evolución a Producto (Completada)

Para llevar el Sandbox al siguiente nivel, hemos planificado 4 etapas cronológicas bajo principios de **Clean Architecture**:

- [x] **1. API Backend (FastAPI):** Exponer el motor RAG a través de una API REST asíncrona, separando la lógica de presentación (Routers) de la lógica de negocio (Services).
- [x] **2. Interfaz de Usuario (UI):** Construir un frontend visual interactivo (Streamlit o Gradio) que consuma los endpoints de FastAPI.
- [x] **3. Agentic RAG:** Añadir capacidades de ruteo inteligente, reescritura de queries y descomposición de preguntas antes de tocar la base de datos.
- [x] **4. Ingestión Multimodal:** Expandir `ingestion.py` para procesar PDFs complejos y analizar imágenes embebidas o sueltas usando `PyMuPDF` y Claude Vision (Anthropic).

---

## 🏆 Roadmap Fase 3: State-of-the-Art (SOTA) Enterprise RAG

- [x] **1. Memoria de Conversación:** Soporte stateful con resolución de correferencias (Chat History).
- [x] **2. Function Calling (Agentes):** Integrar uso de herramientas externas.
- [x] **3. Streaming Real-time (SSE):** Respuestas tipo ChatGPT token-por-token usando `instructor.Partial`.
- [x] **4. Multi-Tenancy y Seguridad:** Autenticación JWT y RLS (Row-Level Security) en Postgres.
- [x] **5. GraphRAG:** Extraer grafos de conocimiento para cruzar entidades (Entity Relationships).

---

## 🔮 Roadmap Fase 4: Nivel Experto (AI Systems Engineering)

Opciones arquitectónicas avanzadas para convertir el Sandbox en un sistema autónomo y optimizado:
- [ ] **1. RAG Evaluator & Observabilidad Activa:** Integración de frameworks como RAGAS/TruLens para calcular métricas (Context Precision, Recall, Faithfulness) en segundo plano.
- [ ] **2. Agentes Multi-Rol (LangGraph):** Orquestación de un equipo de agentes (Supervisor, Investigador, Revisor) con flujos de estado cíclicos, reemplazando el router lineal.
- [ ] **3. Chunking Inteligente:** Semantic Chunking o Hierarchical Chunking (Parent-Child) para maximizar coherencia semántica al fragmentar documentos.
- [x] **4. Transformación de Consultas:** Implementación de HyDE (Hypothetical Document Embeddings) y Multi-Query para hacer la recuperación invulnerable a preguntas ambiguas.
- [ ] **5. Memoria Dinámica a Largo Plazo:** Agente en background que extrae preferencias y hechos del usuario, persistiendo un Perfil Semántico continuo a través de sesiones.
- [ ] **6. Caché Semántico:** Interceptación de preguntas repetidas buscando similitud coseno en la BD para devolver respuestas instantáneas con 0% de costo de inferencia.







---

## 🛠️ Cómo Ejecutar el Entorno Local

1. **Instalar dependencias y gestor uv:**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   uv sync
   ```
2. **Levantar PostgreSQL con pgvector:**
   ```bash
   docker compose up -d
   ```
3. **Configurar el entorno (`.env`):**
   Asegúrate de llenar los valores en el archivo `.env` (copiado de `.env.example`).
   *Nota: Necesitas una llave de Anthropic (`ANTHROPIC_API_KEY`) válida para ejecutar la fase de generación.*
4. **Ingestar un documento:**
   ```bash
   PYTHONPATH=. uv run python src/services/ingestion.py CONTEXT.md
   ```
5. **Probar el Pipeline Completo (Retrieval Híbrido + Rerank + Generación):**
   ```bash
   PYTHONPATH=. uv run python src/pipeline.py "¿Qué base de datos estamos usando y para qué sirve Langfuse?"
   ```
6. **Ejecutar Evals (DeepEval):**
   ```bash
   PYTHONPATH=. uv run pytest tests/test_rag.py
   ```

