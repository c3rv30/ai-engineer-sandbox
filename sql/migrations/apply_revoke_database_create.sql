-- SEC-07: app_user goes from ALL to only CONNECT on the database. ALL included CREATE,
-- which allows creating schemas. With a schema of its own and ALTER ROLE app_user SET
-- search_path (which an ordinary role can set on itself), the application's new
-- connections resolved unqualified tables to app_user's tables, without RLS: whatever
-- any tenant wrote was readable without a signature. The application creates no
-- objects at runtime, so it does not need CREATE. TEMPORARY still comes through
-- PUBLIC, as in any database.
--
-- It leaves the database as 00_create_app_user.sql now creates it. It does not undo a
-- diversion already in place: check first with
--   SELECT * FROM pg_db_role_setting WHERE setrole = 'app_user'::regrole;   -- empty
--   SELECT nspname FROM pg_namespace WHERE nspowner = 'app_user'::regrole;   -- empty
--
-- Run as superuser:
--   psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
--       -f sql/migrations/apply_revoke_database_create.sql

REVOKE ALL PRIVILEGES ON DATABASE postgres FROM app_user;
GRANT CONNECT ON DATABASE postgres TO app_user;
