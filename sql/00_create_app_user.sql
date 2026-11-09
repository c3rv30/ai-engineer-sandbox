CREATE USER app_user WITH PASSWORD 'apppassword';
-- Only CONNECT, not ALL (SEC-07). ALL included CREATE, which allows creating schemas:
-- with one of its own and ALTER ROLE app_user SET search_path, which a role can set on
-- itself, the application's unqualified queries went to app_user's tables without RLS.
GRANT CONNECT ON DATABASE postgres TO app_user;
-- Runs before 01_init.sql: no table exists yet at this point. The FORCE ROW LEVEL
-- SECURITY that used to live in this script is now in 01_init.sql, for all five tables.
--
-- No GRANT on the tables in public and no ALTER DEFAULT PRIVILEGES (HYG-07). The
-- GRANT ... ON ALL TABLES/SEQUENCES did nothing, because there are no tables yet, and
-- ALTER DEFAULT PRIVILEGES handed app_user every table the superuser created later in
-- public, including the ones it must not read; REVOKE ... FROM PUBLIC did not undo it.
-- The application's privileges are granted by 01_init.sql, table by table: a new
-- table is not visible to app_user until it is granted explicitly.
