-- Issue #917 hosted-dev verification found provider-level table privileges
-- that are not constrained by row-level security. The repository never
-- normalized these non-row DDL/maintenance privileges after creating the core
-- tables, so inherited hosted ACLs could remain in place.
--
-- Keep all row-level DML privileges and policies unchanged. Public application
-- flows still depend on their separately reviewed SELECT/INSERT/UPDATE/DELETE
-- grants and RLS policies.

begin;

revoke truncate, trigger, references
    on table
        public.users,
        public.fields,
        public.games,
        public.field_reports,
        public.user_moderation_audit
    from anon, authenticated;

commit;
