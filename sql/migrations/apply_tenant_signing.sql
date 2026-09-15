-- SEC-05: el tenant deja de ser una variable de sesión que app_user pueda reescribir.
-- Ahora viaja junto a una firma HMAC-SHA256 que solo la aplicación sabe calcular, y las
-- políticas RLS consultan una función SECURITY DEFINER que la verifica con una clave
-- guardada donde app_user no puede leerla. Una inyección SQL puede cambiar
-- app.current_tenant, pero no firmarlo: la función devuelve NULL y no ve ninguna fila.
--
-- Se ejecuta como superusuario, con la clave en el entorno:
--   TENANT_SIGNING_KEY=<clave> psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
--       -f sql/migrations/apply_tenant_signing.sql
-- Es la misma clave que la aplicación lee de .env (src/services/db.py).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- La clave vive en su propio esquema, no en public. 00_create_app_user.sql deja un
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public ... GRANT ALL ON TABLES TO app_user, así
-- que toda tabla que el superusuario cree en public nace con un GRANT explícito a
-- app_user, y REVOKE ... FROM PUBLIC no lo deshace. Con la primera versión de esta
-- migración, app_user leía la clave y podía firmar cualquier tenant: comprobado.
CREATE SCHEMA IF NOT EXISTS tenant_security;
REVOKE ALL ON SCHEMA tenant_security FROM PUBLIC;
REVOKE ALL ON SCHEMA tenant_security FROM app_user;

-- Una sola fila: id CHECK (id) fuerza el singleton.
CREATE TABLE IF NOT EXISTS tenant_security.signing_key (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    key TEXT NOT NULL
);
REVOKE ALL ON TABLE tenant_security.signing_key FROM PUBLIC;
REVOKE ALL ON TABLE tenant_security.signing_key FROM app_user;

-- Restos de la primera versión de esta migración, si se llegó a aplicar.
DROP TABLE IF EXISTS public.tenant_signing_key;

-- \getenv deja la variable intacta si la del entorno no existe, así que se predefine
-- vacía para que el DO de abajo dé un error legible en lugar de uno de sintaxis.
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

-- STABLE, no VOLATILE: así el planificador la evalúa una vez por consulta y puede seguir
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
