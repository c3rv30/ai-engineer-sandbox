-- SEC-07: app_user pasa de ALL a solo CONNECT sobre la base. ALL incluía CREATE, que
-- permite crear esquemas. Con un esquema propio y ALTER ROLE app_user SET search_path
-- (que un rol corriente puede fijarse a sí mismo), las conexiones nuevas de la
-- aplicación resolvían las tablas sin esquema en tablas de app_user, sin RLS: lo que
-- escribía cualquier tenant quedaba legible sin firma. La aplicación no crea objetos
-- en tiempo de ejecución, así que no necesita CREATE. TEMPORARY sigue llegando por
-- PUBLIC, como en cualquier base.
--
-- Deja la base igual que la crea ahora 00_create_app_user.sql. No deshace un desvío
-- ya hecho: compruébalo antes con
--   SELECT * FROM pg_db_role_setting WHERE setrole = 'app_user'::regrole;   -- vacío
--   SELECT nspname FROM pg_namespace WHERE nspowner = 'app_user'::regrole;   -- vacío
--
-- Se ejecuta como superusuario:
--   psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
--       -f sql/migrations/apply_revoke_database_create.sql

REVOKE ALL PRIVILEGES ON DATABASE postgres FROM app_user;
GRANT CONNECT ON DATABASE postgres TO app_user;
