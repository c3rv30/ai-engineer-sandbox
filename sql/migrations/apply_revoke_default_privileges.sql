-- HYG-07: retira el privilegio por defecto que 00_create_app_user.sql concedía a
-- app_user sobre toda tabla futura de public. Con él, cualquier tabla que el
-- superusuario creara en public nacía con GRANT ALL a app_user, y REVOKE ... FROM
-- PUBLIC no lo deshacía. Solo afecta a las tablas que se creen a partir de ahora: los
-- GRANT de las cinco tablas de la aplicación son explícitos y se conservan.
--
-- Se ejecuta como superusuario (el privilegio por defecto pertenece a postgres):
--   psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
--       -f sql/migrations/apply_revoke_default_privileges.sql

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON TABLES FROM app_user;
