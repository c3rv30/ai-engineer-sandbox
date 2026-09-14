ALTER TABLE documents ADD COLUMN IF NOT EXISTS tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';
CREATE INDEX IF NOT EXISTS documents_tenant_id_idx ON documents (tenant_id);
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_policy ON documents;
CREATE POLICY tenant_isolation_policy ON documents USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);
