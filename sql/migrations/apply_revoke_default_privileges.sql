-- HYG-07: removes the default privilege that 00_create_app_user.sql granted app_user on
-- every future table in public. With it, any table the superuser created in public was
-- born with GRANT ALL to app_user, and REVOKE ... FROM PUBLIC did not undo it. It only
-- affects tables created from now on: the GRANTs on the application's five tables are
-- explicit and stay.
--
-- Run as superuser (the default privilege belongs to postgres):
--   psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
--       -f sql/migrations/apply_revoke_default_privileges.sql

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON TABLES FROM app_user;
