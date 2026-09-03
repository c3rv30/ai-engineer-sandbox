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
