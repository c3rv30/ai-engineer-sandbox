CREATE USER app_user WITH PASSWORD 'apppassword';
GRANT ALL PRIVILEGES ON DATABASE postgres TO app_user;
-- Se ejecuta antes que 01_init.sql: aquí todavía no existe ninguna tabla. El FORCE ROW
-- LEVEL SECURITY que vivía en este script está ahora en 01_init.sql, para las cinco.
--
-- Sin GRANT sobre las tablas de public y sin ALTER DEFAULT PRIVILEGES (HYG-07). Los
-- GRANT ... ON ALL TABLES/SEQUENCES no hacían nada, porque aún no hay tablas, y el
-- ALTER DEFAULT PRIVILEGES regalaba a app_user toda tabla que el superusuario creara
-- después en public, incluidas las que no debe leer; REVOKE ... FROM PUBLIC no lo
-- deshacía. Los permisos de la aplicación los concede 01_init.sql, tabla por tabla:
-- una tabla nueva no es visible para app_user hasta que se le conceda de forma explícita.
