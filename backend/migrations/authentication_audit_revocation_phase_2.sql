-- ISSUE-1031 phase 2: authorize the exact authentication methods used by
-- the remaining tokens_valid_after mutations. The table shape, RPC, ACLs,
-- indexes, and event taxonomy are unchanged.
--
-- Apply this file as one transaction after authentication_audit_events.sql.

begin;

do $authentication_audit_phase_2_prerequisites$
declare
    audit_table regclass := to_regclass(
        'public.authentication_audit_events'
    );
    trusted_owner oid := to_regrole(current_user);
begin
    if audit_table is null then
        raise exception using
            errcode = '42P01',
            message = 'authentication audit phase-2 migration requires the phase-1 table';
    end if;

    if (
        select table_definition.relowner
        from pg_catalog.pg_class as table_definition
        where table_definition.oid = audit_table
    ) <> trusted_owner then
        raise exception using
            errcode = '42501',
            message = 'authentication audit phase-2 migration must run as the trusted table owner';
    end if;

    if not exists (
        select 1
        from pg_catalog.pg_constraint as constraint_definition
        where constraint_definition.conrelid = audit_table
          and constraint_definition.conname =
              'authentication_audit_events_revocation_method_check'
          and constraint_definition.contype = 'c'
    ) then
        raise exception using
            errcode = 'P0001',
            message = 'authentication audit phase-2 migration requires the phase-1 method constraint';
    end if;
end;
$authentication_audit_phase_2_prerequisites$;

alter table public.authentication_audit_events
drop constraint authentication_audit_events_revocation_method_check;

alter table public.authentication_audit_events
add constraint authentication_audit_events_revocation_method_check check (
    event_type <> 'token_revocation'
    or (
        revocation_reason = 'logout'
        and auth_method = 'bearer'
    )
    or (
        revocation_reason = 'google_unlinked'
        and auth_method = 'password'
    )
    or (
        revocation_reason in ('password_set', 'password_removed')
        and auth_method = 'google'
    )
    or (
        revocation_reason = 'password_reset'
        and auth_method = 'recovery'
    )
    or (
        revocation_reason = 'account_deleted'
        and auth_method in ('password', 'google')
    )
);

commit;
