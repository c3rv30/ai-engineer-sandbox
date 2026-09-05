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
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops);
-- GIN index for full-text search
CREATE INDEX ON documents USING GIN (fts);
-- GIN index for metadata
CREATE INDEX ON documents USING GIN (metadata);
-- Index for tenant_id filtering
CREATE INDEX ON documents (tenant_id);

-- Habilitar Row Level Security (RLS)
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

-- Crear Política de Seguridad RLS
-- Utiliza current_setting('app.current_tenant') para saber el tenant actual
CREATE POLICY tenant_isolation_policy ON documents
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);


-- Fase 4: Semantic Cache
CREATE TABLE IF NOT EXISTS semantic_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    query_text TEXT NOT NULL,
    query_embedding vector(384),
    response_json JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ON semantic_cache USING hnsw (query_embedding vector_cosine_ops);
CREATE INDEX ON semantic_cache(tenant_id);
ALTER TABLE semantic_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY cache_tenant_isolation_policy ON semantic_cache 
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);

-- Fase 4: Long-Term Memory
CREATE TABLE IF NOT EXISTS user_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    fact TEXT NOT NULL,
    fact_embedding vector(384),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ON user_memory USING hnsw (fact_embedding vector_cosine_ops);
CREATE INDEX ON user_memory(tenant_id);
ALTER TABLE user_memory ENABLE ROW LEVEL SECURITY;
CREATE POLICY memory_tenant_isolation_policy ON user_memory 
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);

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
CREATE INDEX ON rag_evaluations(tenant_id);
ALTER TABLE rag_evaluations ENABLE ROW LEVEL SECURITY;
CREATE POLICY evaluations_tenant_isolation_policy ON rag_evaluations 
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);
