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

ALTER TABLE knowledge_graph ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_graph FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS kg_tenant_isolation_policy ON knowledge_graph;
CREATE POLICY kg_tenant_isolation_policy ON knowledge_graph 
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);
    
GRANT ALL PRIVILEGES ON TABLE knowledge_graph TO app_user;
