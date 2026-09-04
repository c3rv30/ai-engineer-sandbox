CREATE TABLE IF NOT EXISTS user_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    fact TEXT NOT NULL,
    fact_embedding vector(384),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS memory_embedding_idx ON user_memory USING hnsw (fact_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS memory_tenant_idx ON user_memory(tenant_id);

ALTER TABLE user_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_memory FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS memory_tenant_isolation_policy ON user_memory;
CREATE POLICY memory_tenant_isolation_policy ON user_memory 
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);
    
GRANT ALL PRIVILEGES ON TABLE user_memory TO app_user;
