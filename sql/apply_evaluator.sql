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

ALTER TABLE rag_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_evaluations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS evaluations_tenant_isolation_policy ON rag_evaluations;
CREATE POLICY evaluations_tenant_isolation_policy ON rag_evaluations 
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);
    
GRANT ALL PRIVILEGES ON TABLE rag_evaluations TO app_user;
