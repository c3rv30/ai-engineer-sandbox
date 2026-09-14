-- Esquema completo del sandbox. Lo ejecuta el entrypoint de Postgres sobre un volumen
-- vacío, en orden alfabético y después de 00_create_app_user.sql, que crea el rol al
-- que se conceden los permisos del final. Los scripts de sql/migrations/ son el
-- histórico con el que se construyó la base de desarrollo; aquí está su resultado.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    content TEXT,
    embedding vector(384),
    metadata JSONB,
    fts tsvector GENERATED ALWAYS AS (to_tsvector('spanish', content)) STORED
);

-- HNSW index for vector search
CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents USING hnsw (embedding vector_cosine_ops);
-- GIN index for full-text search
CREATE INDEX IF NOT EXISTS documents_fts_idx ON documents USING GIN (fts);
-- GIN index for metadata
CREATE INDEX IF NOT EXISTS documents_metadata_idx ON documents USING GIN (metadata);
-- Index for tenant_id filtering
CREATE INDEX IF NOT EXISTS documents_tenant_id_idx ON documents (tenant_id);


-- Fase 4: Semantic Cache
CREATE TABLE IF NOT EXISTS semantic_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    query_text TEXT NOT NULL,
    query_embedding vector(384),
    response_json JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS cache_embedding_idx ON semantic_cache USING hnsw (query_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS cache_tenant_idx ON semantic_cache(tenant_id);

-- Fase 4: Long-Term Memory
CREATE TABLE IF NOT EXISTS user_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    fact TEXT NOT NULL,
    fact_embedding vector(384),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS memory_embedding_idx ON user_memory USING hnsw (fact_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS memory_tenant_idx ON user_memory(tenant_id);

-- Fase 4: Observabilidad Activa (Evaluaciones RAG)
CREATE TABLE IF NOT EXISTS rag_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    query TEXT NOT NULL,
    faithfulness_score FLOAT CHECK (faithfulness_score >= 0.0 AND faithfulness_score <= 1.0),
    relevance_score FLOAT CHECK (relevance_score >= 0.0 AND relevance_score <= 1.0),
    context_precision_score FLOAT CHECK (context_precision_score >= 0.0 AND context_precision_score <= 1.0),
    reasoning TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS evaluations_tenant_idx ON rag_evaluations(tenant_id);

-- Fase 3: GraphRAG
CREATE TABLE IF NOT EXISTS knowledge_graph (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    source_node VARCHAR(255) NOT NULL,
    relation VARCHAR(255) NOT NULL,
    target_node VARCHAR(255) NOT NULL,
    source_chunk_id UUID REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS kg_source_idx ON knowledge_graph(source_node);
CREATE INDEX IF NOT EXISTS kg_target_idx ON knowledge_graph(target_node);
CREATE INDEX IF NOT EXISTS kg_tenant_idx ON knowledge_graph(tenant_id);


-- Row Level Security. FORCE hace que las políticas se apliquen también al propietario
-- de las tablas; sin él, el propietario las elude. Un superusuario las elude siempre,
-- con o sin FORCE: por eso la aplicación debe conectar como app_user.
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
ALTER TABLE semantic_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE semantic_cache FORCE ROW LEVEL SECURITY;
ALTER TABLE user_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_memory FORCE ROW LEVEL SECURITY;
ALTER TABLE rag_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_evaluations FORCE ROW LEVEL SECURITY;
ALTER TABLE knowledge_graph ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_graph FORCE ROW LEVEL SECURITY;

-- Utiliza current_setting('app.current_tenant') para saber el tenant actual
DROP POLICY IF EXISTS tenant_isolation_policy ON documents;
CREATE POLICY tenant_isolation_policy ON documents
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);
DROP POLICY IF EXISTS cache_tenant_isolation_policy ON semantic_cache;
CREATE POLICY cache_tenant_isolation_policy ON semantic_cache
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);
DROP POLICY IF EXISTS memory_tenant_isolation_policy ON user_memory;
CREATE POLICY memory_tenant_isolation_policy ON user_memory
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);
DROP POLICY IF EXISTS evaluations_tenant_isolation_policy ON rag_evaluations;
CREATE POLICY evaluations_tenant_isolation_policy ON rag_evaluations
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);
DROP POLICY IF EXISTS kg_tenant_isolation_policy ON knowledge_graph;
CREATE POLICY kg_tenant_isolation_policy ON knowledge_graph
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);

-- Explícitos aunque 00_create_app_user.sql fije privilegios por defecto: así el script
-- no depende de cómo se creó el rol.
GRANT ALL PRIVILEGES ON TABLE documents, semantic_cache, user_memory, rag_evaluations, knowledge_graph TO app_user;
