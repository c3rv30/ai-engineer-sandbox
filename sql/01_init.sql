-- Full sandbox schema. The Postgres entrypoint runs it on an empty volume, in
-- alphabetical order and after 00_create_app_user.sql, which creates the role the
-- privileges at the end are granted to. The scripts in sql/migrations/ are the history
-- the development database was built with; this is their result.

CREATE EXTENSION IF NOT EXISTS vector;
-- hmac() to verify the signature of the tenant context (SEC-05).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    content TEXT,
    embedding vector(384),
    metadata JSONB,
    -- 'spanish': the language of the corpus. The retriever queries with the same
    -- configuration (src/services/retriever.py).
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


-- Phase 4: Semantic Cache
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

-- Phase 4: Long-Term Memory
CREATE TABLE IF NOT EXISTS user_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    fact TEXT NOT NULL,
    fact_embedding vector(384),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS memory_embedding_idx ON user_memory USING hnsw (fact_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS memory_tenant_idx ON user_memory(tenant_id);

-- Phase 4: Active observability (RAG evaluations)
CREATE TABLE IF NOT EXISTS rag_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    query TEXT NOT NULL,
    faithfulness_score FLOAT CHECK (faithfulness_score >= 0.0 AND faithfulness_score <= 1.0),
    relevance_score FLOAT CHECK (relevance_score >= 0.0 AND relevance_score <= 1.0),
    context_precision_score FLOAT CHECK (context_precision_score >= 0.0 AND context_precision_score <= 1.0),
    reasoning TEXT,
    -- Language the supervisor decided and language detected in the answer (BUG-11).
    -- NULL for rows from before and for an answer whose language could not be told.
    expected_language TEXT CHECK (expected_language IN ('es', 'en')),
    detected_language TEXT CHECK (detected_language IN ('es', 'en')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS evaluations_tenant_idx ON rag_evaluations(tenant_id);

-- Phase 3: GraphRAG
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


-- Row Level Security. FORCE makes the policies apply to the tables' owner too; without
-- it, the owner bypasses them. A superuser always bypasses them, with or without FORCE:
-- that is why the application must connect as app_user.
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

-- Signed tenant context (SEC-05). The policies do not read app.current_tenant
-- directly: app_user itself can rewrite a session variable from any injected
-- statement. They read app_current_tenant(), which returns the tenant only if it comes
-- with an HMAC signature computed with the key below, which app_user cannot read. The
-- details are in sql/migrations/apply_tenant_signing.sql.
--
-- The key lives in its own schema, not in public. Until HYG-07, 00_create_app_user.sql
-- left an ALTER DEFAULT PRIVILEGES IN SCHEMA public ... GRANT ALL ON TABLES TO
-- app_user, and a table in public was born readable by app_user; the separate schema,
-- with its explicit REVOKEs, does not depend on that default privilege never coming back.
CREATE SCHEMA IF NOT EXISTS tenant_security;
REVOKE ALL ON SCHEMA tenant_security FROM PUBLIC;
REVOKE ALL ON SCHEMA tenant_security FROM app_user;

CREATE TABLE IF NOT EXISTS tenant_security.signing_key (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    key TEXT NOT NULL
);
REVOKE ALL ON TABLE tenant_security.signing_key FROM PUBLIC;
REVOKE ALL ON TABLE tenant_security.signing_key FROM app_user;

-- \getenv leaves the variable untouched if the environment one does not exist, so it
-- is predefined empty for the DO below to give a readable error instead of a syntax one.
-- The entrypoint runs with ON_ERROR_STOP=1: without a key, the container exits (like BUG-04).
\set tenant_key ''
\getenv tenant_key TENANT_SIGNING_KEY

-- Through a session GUC because psql does not substitute variables inside $$...$$.
SELECT set_config('init.tenant_key', :'tenant_key', FALSE);

DO $$
DECLARE k TEXT := NULLIF(current_setting('init.tenant_key', TRUE), '');
BEGIN
    IF k IS NULL OR length(k) < 32 THEN
        RAISE EXCEPTION 'TENANT_SIGNING_KEY is missing or shorter than 32 characters. Generate one with: openssl rand -hex 32';
    END IF;
    INSERT INTO tenant_security.signing_key (key) VALUES (k)
        ON CONFLICT (id) DO UPDATE SET key = EXCLUDED.key;
END $$;

-- STABLE, not VOLATILE: the planner evaluates it once per query and can keep using the
-- tenant_id indexes, instead of computing the HMAC row by row.
-- Fixed search_path: without it, a role with create privileges could put a schema with
-- its own hmac() first and make the function validate any signature.
CREATE OR REPLACE FUNCTION app_current_tenant() RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, tenant_security, public
AS $$
    -- CASE evaluates in order: the ::UUID only runs on an already verified value, so a
    -- malformed tenant returns NULL instead of breaking the query.
    SELECT CASE
        WHEN ctx.tenant IS NULL OR ctx.sig IS NULL OR k.key IS NULL THEN NULL
        WHEN encode(hmac(ctx.tenant, k.key, 'sha256'), 'hex') = ctx.sig THEN ctx.tenant::UUID
        ELSE NULL
    END
    FROM (
        SELECT NULLIF(current_setting('app.current_tenant', TRUE), '') AS tenant,
               NULLIF(current_setting('app.tenant_signature', TRUE), '') AS sig
    ) ctx
    LEFT JOIN tenant_security.signing_key k ON TRUE;
$$;

REVOKE ALL ON FUNCTION app_current_tenant() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_current_tenant() TO app_user;

DROP POLICY IF EXISTS tenant_isolation_policy ON documents;
CREATE POLICY tenant_isolation_policy ON documents
    USING (tenant_id = app_current_tenant());
DROP POLICY IF EXISTS cache_tenant_isolation_policy ON semantic_cache;
CREATE POLICY cache_tenant_isolation_policy ON semantic_cache
    USING (tenant_id = app_current_tenant());
DROP POLICY IF EXISTS memory_tenant_isolation_policy ON user_memory;
CREATE POLICY memory_tenant_isolation_policy ON user_memory
    USING (tenant_id = app_current_tenant());
DROP POLICY IF EXISTS evaluations_tenant_isolation_policy ON rag_evaluations;
CREATE POLICY evaluations_tenant_isolation_policy ON rag_evaluations
    USING (tenant_id = app_current_tenant());
DROP POLICY IF EXISTS kg_tenant_isolation_policy ON knowledge_graph;
CREATE POLICY kg_tenant_isolation_policy ON knowledge_graph
    USING (tenant_id = app_current_tenant());

-- app_user's only privileges on tables: there are no default privileges in public
-- (HYG-07). A new table the application must use needs its own GRANT.
GRANT ALL PRIVILEGES ON TABLE documents, semantic_cache, user_memory, rag_evaluations, knowledge_graph TO app_user;
