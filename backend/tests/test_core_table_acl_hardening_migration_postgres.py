"""Real PostgreSQL checks for Issue #917 core-table ACL hardening.

Set CORE_TABLE_ACL_DATABASE_URL to a disposable PostgreSQL database. These
tests destroy and recreate the public schema and must never target a shared
database.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest


DATABASE_URL = os.getenv("CORE_TABLE_ACL_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="CORE_TABLE_ACL_DATABASE_URL is not configured",
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND_DIR / "migrations" / "core_table_acl_hardening.sql"
SCHEMA = BACKEND_DIR / "schema.sql"
TABLES = (
    "users",
    "fields",
    "games",
    "field_reports",
    "user_moderation_audit",
)
ROLES = ("anon", "authenticated")
DML_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE"}
DANGEROUS_PRIVILEGES = {"TRUNCATE", "TRIGGER", "REFERENCES"}


def execute(sql: str, params: tuple = (), *, fetch: bool = False):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params if params else None)
            return cursor.fetchall() if fetch else None


def run_migration() -> None:
    execute(MIGRATION.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def clean_database() -> None:
    execute(
        """
        drop schema if exists public cascade;
        create schema public;

        do $$
        begin
            create role anon nologin;
        exception when duplicate_object then null;
        end
        $$;
        do $$
        begin
            create role authenticated nologin;
        exception when duplicate_object then null;
        end
        $$;

        create table public.users (id uuid primary key);
        create table public.fields (id uuid primary key);
        create table public.games (id uuid primary key);
        create table public.field_reports (
            id uuid primary key,
            user_id uuid not null
        );
        create table public.user_moderation_audit (id uuid primary key);

        alter table public.users enable row level security;
        alter table public.fields enable row level security;
        alter table public.games enable row level security;
        alter table public.field_reports enable row level security;
        alter table public.user_moderation_audit enable row level security;

        create policy field_reports_select_test
            on public.field_reports for select
            to anon, authenticated
            using (true);
        create policy field_reports_insert_test
            on public.field_reports for insert
            to anon, authenticated
            with check (true);

        grant select, insert, update, delete, truncate, trigger, references
            on table
                public.users,
                public.fields,
                public.games,
                public.field_reports,
                public.user_moderation_audit
            to anon, authenticated;
        """
    )


def acl_snapshot() -> list[tuple[str, str, str]]:
    return execute(
        """
        select grantee, table_name, privilege_type
        from information_schema.role_table_grants
        where table_schema = 'public'
          and grantee = any(%s)
          and table_name = any(%s)
        order by grantee, table_name, privilege_type
        """,
        (list(ROLES), list(TABLES)),
        fetch=True,
    )


def policy_snapshot() -> list[tuple]:
    return execute(
        """
        select schemaname, tablename, policyname, permissive, roles, cmd,
               qual, with_check
        from pg_catalog.pg_policies
        where schemaname = 'public'
          and tablename = any(%s)
        order by tablename, policyname
        """,
        (list(TABLES),),
        fetch=True,
    )


def rls_snapshot() -> list[tuple[str, bool, bool]]:
    return execute(
        """
        select table_definition.relname,
               table_definition.relrowsecurity,
               table_definition.relforcerowsecurity
        from pg_catalog.pg_class as table_definition
        join pg_catalog.pg_namespace as schema_definition
          on schema_definition.oid = table_definition.relnamespace
        where schema_definition.nspname = 'public'
          and table_definition.relname = any(%s)
        order by table_definition.relname
        """,
        (list(TABLES),),
        fetch=True,
    )


def privilege_matrix() -> dict[tuple[str, str], set[str]]:
    matrix = {(role, table): set() for role in ROLES for table in TABLES}
    for role, table, privilege in acl_snapshot():
        matrix[(role, table)].add(privilege)
    return matrix


def effective_dangerous_privileges() -> list[tuple[str, str, str]]:
    return execute(
        """
        select role_name, table_name, privilege_name
        from unnest(%s::text[]) as role_name
        cross join unnest(%s::text[]) as table_name
        cross join unnest(%s::text[]) as privilege_name
        where pg_catalog.has_table_privilege(
            role_name,
            pg_catalog.format('public.%%I', table_name),
            privilege_name
        )
        order by role_name, table_name, privilege_name
        """,
        (list(ROLES), list(TABLES), sorted(DANGEROUS_PRIVILEGES)),
        fetch=True,
    )


def test_migration_removes_dangerous_privileges_and_preserves_dml() -> None:
    before = privilege_matrix()
    assert all(
        privileges == DML_PRIVILEGES | DANGEROUS_PRIVILEGES
        for privileges in before.values()
    )

    run_migration()

    after = privilege_matrix()
    assert all(privileges == DML_PRIVILEGES for privileges in after.values())
    assert effective_dangerous_privileges() == []


def test_migration_preserves_rls_and_policy_catalogs_exactly() -> None:
    policies_before = policy_snapshot()
    rls_before = rls_snapshot()

    run_migration()

    assert policy_snapshot() == policies_before
    assert rls_snapshot() == rls_before


def test_migration_reapplication_is_catalog_idempotent() -> None:
    run_migration()
    first_acl = acl_snapshot()
    first_policies = policy_snapshot()
    first_rls = rls_snapshot()

    run_migration()

    assert acl_snapshot() == first_acl
    assert policy_snapshot() == first_policies
    assert rls_snapshot() == first_rls


def test_fresh_schema_repairs_provider_style_default_privileges() -> None:
    execute(
        """
        drop schema public cascade;
        create schema public;
        create schema if not exists auth;
        create or replace function auth.uid()
        returns uuid
        language sql
        stable
        as $auth_uid$
            select null::uuid
        $auth_uid$;
        do $$
        begin
            create role service_role nologin bypassrls;
        exception when duplicate_object then null;
        end
        $$;
        grant usage on schema public to service_role, anon, authenticated;
        alter default privileges in schema public
            grant select, insert, update, delete, truncate, trigger, references
            on tables to anon, authenticated;
        """
    )
    try:
        execute(SCHEMA.read_text(encoding="utf-8"))

        after = privilege_matrix()
        assert all(
            privileges == DML_PRIVILEGES for privileges in after.values()
        )
        assert effective_dangerous_privileges() == []
    finally:
        execute(
            """
            alter default privileges in schema public
                revoke select, insert, update, delete, truncate, trigger,
                       references
                on tables from anon, authenticated;
            """
        )


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("table", TABLES)
def test_truncate_is_denied_after_migration(role: str, table: str) -> None:
    run_migration()

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        execute(f"set role {role}; truncate table public.{table}")
