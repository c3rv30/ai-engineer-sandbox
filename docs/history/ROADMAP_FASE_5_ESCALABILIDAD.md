# 🗺️ Roadmap Fase 5: Escalamiento y DevOps (Trabajo Futuro)

Este documento detalla las 5 iniciativas estratégicas (Epics) identificadas al finalizar la Fase 4 para llevar el sistema de un "Sandbox" a una arquitectura nativa de nube (Cloud-Native) completamente escalable y observable.

---

### 1. 🐳 Contenerización Total (DevOps & Deploy)
Actualmente, la orquestación depende de que el host posea Python instalado localmente, relegando el uso de Docker únicamente a la capa de PostgreSQL.
- **Objetivo:** Empaquetar la aplicación completa para despliegues *serverless* (ej. Google Cloud Run, AWS ECS).
- **Tareas Técnicas:**
  - Crear un `Dockerfile` optimizado (Multi-stage build) utilizando `uv` para minimizar el tamaño de la imagen y los tiempos de compilación.
  - Actualizar `docker-compose.yml` para levantar la base de datos, el backend (FastAPI) y el frontend (Streamlit) en una misma red virtual.
  - Configurar variables de entorno y *Healthchecks*.

### 2. 📊 Dashboard Analítico de Evaluaciones (Data Viz)
El agente pasivo (LLM-as-a-judge) evalúa constantemente el sistema, pero los datos están ocultos en la base de datos sin explotarse visualmente.
- **Objetivo:** Proveer una ventana de observabilidad para detectar degradaciones del modelo.
- **Tareas Técnicas:**
  - Crear una nueva pestaña/página en Streamlit (`Dashboard.py`).
  - Desarrollar endpoints en FastAPI para consultar métricas agregadas.
  - Utilizar librerías como `altair` o `plotly` para renderizar series de tiempo mostrando la evolución de *Faithfulness*, *Relevance* y *Context Precision*.

### 3. 🧹 Garbage Collector para Caché Semántico (Eviction Policy)
El caché semántico (`semantic_cache`) inserta consultas perpetuamente, lo que eventualmente saturará la memoria RAM y corromperá la velocidad de recuperación del índice HNSW.
- **Objetivo:** Implementar una política de desalojo (Time-To-Live).
- **Tareas Técnicas:**
  - Crear una tarea periódica (CRON Job) en FastAPI utilizando `APScheduler` o `asyncio`.
  - Diseñar una consulta SQL asíncrona que ejecute un barrido (`DELETE`) de las filas cuyo campo `created_at` exceda un umbral configurado (ej. 7 días).

### 4. 🌐 Búsqueda Léxica Multilingüe Dinámica (BM25)
La configuración del *Full-Text Search* nativo de PostgreSQL utiliza actualmente una coerción dura: `to_tsvector('spanish', content)`. Si se ingieren documentos en otros idiomas, el *stemming* y las *stop words* fallarán catastróficamente.
- **Objetivo:** Hacer que la base de datos respete el idioma original del fragmento.
- **Tareas Técnicas:**
  - Integrar una librería de detección de idiomas (como `langdetect` o `lingua-py`) en el pipeline de ingesta (`src/services/ingestion.py`).
  - Modificar el esquema SQL para aceptar el idioma como una columna y generar el vector dinámicamente, o forzar la inyección paramétrica del idioma en las queries del Retriever.

### 5. 🕸️ GraphRAG Avanzado (Graph Theory Topológica)
La implementación actual de GraphRAG extrae eficientemente nodos, pero su recuperación utiliza una expresión regular plana de 1 salto (1-hop), ignorando el peso real de las relaciones comunitarias.
- **Objetivo:** Proveer al modelo de un subgrafo de contexto matemáticamente central.
- **Tareas Técnicas:**
  - Implementar la librería `NetworkX` o migrar los datos a un motor nativo de grafos como `Neo4j` / `Apache Age`.
  - Computar algoritmos de *PageRank*, detección de comunidades (*Leiden*) o *Betweenness Centrality* sobre las tripletas almacenadas antes de inyectarlas en el contexto del nodo Generador.
