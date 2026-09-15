-- Esquema completo del sandbox. Lo ejecuta el entrypoint de Postgres sobre un volumen
-- vacío, en orden alfabético y después de 00_create_app_user.sql, que crea el rol al
-- que se conceden los permisos del final. Los scripts de sql/migrations/ son el
-- histórico con el que se construyó la base de desarrollo; aquí está su resultado.

CREATE EXTENSION IF NOT EXISTS vector;
-- hmac() para verificar la firma del contexto de tenant (SEC-05).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

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

-- Contexto de tenant firmado (SEC-05). Las políticas no leen app.current_tenant
-- directamente: una variable de sesión la puede reescribir el propio app_user desde
-- cualquier sentencia inyectada. Leen app_current_tenant(), que solo devuelve el tenant
-- si viene acompañado de una firma HMAC calculada con la clave de abajo, que app_user
-- no puede leer. El detalle está en sql/migrations/apply_tenant_signing.sql.
--
-- La clave vive en su propio esquema, no en public: 00_create_app_user.sql deja un
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public ... GRANT ALL ON TABLES TO app_user, así
-- que toda tabla que el superusuario cree en public nace con un GRANT explícito a
-- app_user, y REVOKE ... FROM PUBLIC no lo deshace.
CREATE SCHEMA IF NOT EXISTS tenant_security;
REVOKE ALL ON SCHEMA tenant_security FROM PUBLIC;
REVOKE ALL ON SCHEMA tenant_security FROM app_user;

CREATE TABLE IF NOT EXISTS tenant_security.signing_key (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    key TEXT NOT NULL
);
REVOKE ALL ON TABLE tenant_security.signing_key FROM PUBLIC;
REVOKE ALL ON TABLE tenant_security.signing_key FROM app_user;

-- \getenv deja la variable intacta si la del entorno no existe, así que se predefine
-- vacía para que el DO de abajo dé un error legible en lugar de uno de sintaxis.
-- El entrypoint corre con ON_ERROR_STOP=1: sin clave, el contenedor sale (como BUG-04).
\set tenant_key ''
\getenv tenant_key TENANT_SIGNING_KEY

-- Vía una GUC de sesión porque psql no sustituye variables dentro de $$...$$.
SELECT set_config('init.tenant_key', :'tenant_key', FALSE);

DO $$
DECLARE k TEXT := NULLIF(current_setting('init.tenant_key', TRUE), '');
BEGIN
    IF k IS NULL OR length(k) < 32 THEN
        RAISE EXCEPTION 'TENANT_SIGNING_KEY ausente o de menos de 32 caracteres. Genera una con: openssl rand -hex 32';
    END IF;
    INSERT INTO tenant_security.signing_key (key) VALUES (k)
        ON CONFLICT (id) DO UPDATE SET key = EXCLUDED.key;
END $$;

-- STABLE, no VOLATILE: el planificador la evalúa una vez por consulta y puede seguir
-- usando los índices por tenant_id, en lugar de calcular el HMAC fila a fila.
-- search_path fijo: sin él, un rol con permiso de creación podría anteponer un esquema
-- con su propia hmac() y hacer que la función valide cualquier firma.
CREATE OR REPLACE FUNCTION app_current_tenant() RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, tenant_security, public
AS $$
    -- El CASE evalúa en orden: el ::UUID solo se ejecuta sobre un valor ya verificado,
    -- así que un tenant malformado devuelve NULL en vez de reventar la consulta.
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

-- Explícitos aunque 00_create_app_user.sql fije privilegios por defecto: así el script
-- no depende de cómo se creó el rol.
GRANT ALL PRIVILEGES ON TABLE documents, semantic_cache, user_memory, rag_evaluations, knowledge_graph TO app_user;
