-- SEC-05: the tenant is no longer a session variable app_user can rewrite. It now
-- travels with an HMAC-SHA256 signature only the application can compute, and the RLS
-- policies call a SECURITY DEFINER function that verifies it with a key stored where
-- app_user cannot read it. An SQL injection can change app.current_tenant, but not sign
-- it: the function returns NULL and no row is visible.
--
-- Run as superuser, with the key in the environment:
--   TENANT_SIGNING_KEY=<key> psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
--       -f sql/migrations/apply_tenant_signing.sql
-- It is the same key the application reads from .env (src/services/db.py).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- The key lives in its own schema, not in public. 00_create_app_user.sql leaves an
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public ... GRANT ALL ON TABLES TO app_user, so
-- every table the superuser creates in public is born with an explicit GRANT to
-- app_user, and REVOKE ... FROM PUBLIC does not undo it. With the first version of this
-- migration, app_user read the key and could sign any tenant: verified.
CREATE SCHEMA IF NOT EXISTS tenant_security;
REVOKE ALL ON SCHEMA tenant_security FROM PUBLIC;
REVOKE ALL ON SCHEMA tenant_security FROM app_user;

-- A single row: id CHECK (id) enforces the singleton.
CREATE TABLE IF NOT EXISTS tenant_security.signing_key (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    key TEXT NOT NULL
);
REVOKE ALL ON TABLE tenant_security.signing_key FROM PUBLIC;
REVOKE ALL ON TABLE tenant_security.signing_key FROM app_user;

-- Leftovers of the first version of this migration, if it was ever applied.
DROP TABLE IF EXISTS public.tenant_signing_key;

-- \getenv leaves the variable untouched if the environment one does not exist, so it
-- is predefined empty for the DO below to give a readable error instead of a syntax one.
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

-- STABLE, not VOLATILE: that way the planner evaluates it once per query and can keep
-- using the tenant_id indexes, instead of computing the HMAC row by row.
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
