"""Real PostgreSQL checks for ISSUE-1031 authentication-audit retention.

Set AUTHENTICATION_AUDIT_DATABASE_URL to a disposable database. These tests
destroy and recreate the public schema and must never target a shared database.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest


DATABASE_URL = os.getenv("AUTHENTICATION_AUDIT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="AUTHENTICATION_AUDIT_DATABASE_URL is not configured",
)

BACKEND_DIR = Path(__file__).parents[1]
AUDIT_MIGRATION = (
    BACKEND_DIR / "migrations" / "authentication_audit_events.sql"
)
PHASE_2_MIGRATION = (
    BACKEND_DIR / "migrations" / "authentication_audit_revocation_phase_2.sql"
)
RETENTION_MIGRATION = (
    BACKEND_DIR / "migrations" / "authentication_audit_retention.sql"
)
PREFLIGHT = (
    BACKEND_DIR
    / "scripts"
    / "authentication_audit_retention_migration_preflight.sql"
)
VERIFICATION = (
    BACKEND_DIR
    / "scripts"
    / "verify_authentication_audit_retention_migration.sql"
)
SCHEMA = BACKEND_DIR / "schema.sql"

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=180)


def execute(sql: str, params: tuple = (), *, fetch: bool = False):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params if params else None)
            return cursor.fetchall() if fetch else None


def execute_as(
    role: str,
    sql: str,
    params: tuple = (),
    *,
    fetch: bool = False,
):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"set role {role}")
            cursor.execute(sql, params if params else None)
            return cursor.fetchall() if fetch else None


def execute_as_session(
    role: str,
    sql: str,
    params: tuple = (),
    *,
    fetch: bool = False,
):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"set session authorization {role}")
            cursor.execute(sql, params if params else None)
            return cursor.fetchall() if fetch else None


def run_sql_file(path: Path) -> None:
    execute(path.read_text(encoding="utf-8"))


def run_sql_file_as_session(role: str, path: Path) -> None:
    execute_as_session(role, path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def clean_database() -> None:
    execute(
        """
        drop schema if exists public cascade;
        create schema public;
        do $$
        begin
            create role service_role nologin bypassrls;
        exception when duplicate_object then null;
        end
        $$;
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
        do $$
        begin
            create role retention_rogue nologin;
        exception when duplicate_object then null;
        end
        $$;
        do $$
        begin
            create role retention_acl_migrator nologin noinherit;
        exception when duplicate_object then null;
        end
        $$;
        alter role service_role bypassrls;
        alter role retention_acl_migrator noinherit;
        grant usage on schema public to service_role, anon, authenticated;
        grant usage, create on schema public to retention_acl_migrator;
        do $$
        begin
            if current_setting('server_version_num')::integer >= 160000 then
                execute
                    'grant service_role to retention_acl_migrator '
                    'with set true';
                execute
                    'grant anon, authenticated to retention_acl_migrator '
                    'with set true';
            else
                execute 'grant service_role to retention_acl_migrator';
                execute
                    'grant anon, authenticated to retention_acl_migrator';
            end if;
        end
        $$;
        create table public.users (
            id uuid primary key,
            email text,
            name text not null
        );
        grant select, insert, update, delete, references
        on table public.users to retention_acl_migrator;
        """
    )


def apply_audit_prerequisites() -> None:
    run_sql_file(AUDIT_MIGRATION)
    run_sql_file(PHASE_2_MIGRATION)


def apply_retention() -> None:
    apply_audit_prerequisites()
    run_sql_file(RETENTION_MIGRATION)


def apply_audit_prerequisites_as_session(role: str) -> None:
    run_sql_file_as_session(role, AUDIT_MIGRATION)
    run_sql_file_as_session(role, PHASE_2_MIGRATION)


def apply_retention_as_session(role: str) -> None:
    apply_audit_prerequisites_as_session(role)
    run_sql_file_as_session(role, RETENTION_MIGRATION)


def insert_event(event_id: str, occurred_at: datetime) -> None:
    execute(
        """
        insert into public.authentication_audit_events (
            id,
            occurred_at,
            event_type,
            outcome,
            auth_method,
            user_id,
            failure_category,
            revocation_reason,
            correlation_id,
            source_environment
        )
        values (%s, %s, 'login', 'succeeded', 'password',
                null, null, null, %s, 'test')
        """,
        (event_id, occurred_at, f"retention-{event_id[-12:]}"),
    )


def cleanup_as(role: str, cutoff: datetime, limit: int) -> int:
    return execute_as(
        role,
        """
        select public.cleanup_authentication_audit_events(%s, %s)
        """,
        (cutoff, limit),
        fetch=True,
    )[0][0]


def retention_snapshot() -> dict[str, list[tuple]]:
    return {
        "function": execute(
            """
            select
                pg_catalog.pg_get_userbyid(function_definition.proowner),
                pg_catalog.pg_get_function_identity_arguments(
                    function_definition.oid
                ),
                pg_catalog.pg_get_function_result(function_definition.oid),
                function_definition.prosecdef,
                function_definition.provolatile,
                function_definition.proparallel,
                function_definition.proconfig,
                function_definition.prosrc
            from pg_catalog.pg_proc as function_definition
            where function_definition.oid =
                  'public.cleanup_authentication_audit_events(timestamptz,integer)'::regprocedure
            """,
            fetch=True,
        ),
        "function_acl": execute(
            """
            select
                coalesce(role_definition.rolname, 'PUBLIC'),
                privilege.privilege_type,
                privilege.is_grantable
            from pg_catalog.pg_proc as function_definition
            cross join lateral pg_catalog.aclexplode(
                coalesce(
                    function_definition.proacl,
                    pg_catalog.acldefault('f', function_definition.proowner)
                )
            ) as privilege
            left join pg_catalog.pg_roles as role_definition
              on role_definition.oid = privilege.grantee
            where function_definition.oid =
                  'public.cleanup_authentication_audit_events(timestamptz,integer)'::regprocedure
            order by 1, 2
            """,
            fetch=True,
        ),
        "table_security": execute(
            """
            select
                pg_catalog.pg_get_userbyid(table_definition.relowner),
                table_definition.relrowsecurity,
                table_definition.relforcerowsecurity
            from pg_catalog.pg_class as table_definition
            where table_definition.oid =
                  'public.authentication_audit_events'::regclass
            """,
            fetch=True,
        ),
        "table_acl": execute(
            """
            select
                coalesce(role_definition.rolname, 'PUBLIC'),
                privilege.privilege_type,
                privilege.is_grantable
            from pg_catalog.pg_class as table_definition
            cross join lateral pg_catalog.aclexplode(
                coalesce(
                    table_definition.relacl,
                    pg_catalog.acldefault('r', table_definition.relowner)
                )
            ) as privilege
            left join pg_catalog.pg_roles as role_definition
              on role_definition.oid = privilege.grantee
            where table_definition.oid =
                  'public.authentication_audit_events'::regclass
            order by 1, 2
            """,
            fetch=True,
        ),
        "column_acl": execute(
            """
            select
                attribute_definition.attname,
                coalesce(role_definition.rolname, 'PUBLIC'),
                privilege.privilege_type,
                privilege.is_grantable
            from pg_catalog.pg_attribute as attribute_definition
            cross join lateral pg_catalog.aclexplode(
                attribute_definition.attacl
            ) as privilege
            left join pg_catalog.pg_roles as role_definition
              on role_definition.oid = privilege.grantee
            where attribute_definition.attrelid =
                  'public.authentication_audit_events'::regclass
              and attribute_definition.attnum > 0
              and not attribute_definition.attisdropped
            order by 1, 2, 3
            """,
            fetch=True,
        ),
        "occurred_at_index": execute(
            """
            select
                pg_catalog.pg_get_indexdef(index_definition.indexrelid),
                index_definition.indisvalid,
                index_definition.indisready,
                index_definition.indislive
            from pg_catalog.pg_index as index_definition
            where index_definition.indexrelid =
                  'public.idx_authentication_audit_events_occurred_at'::regclass
            """,
            fetch=True,
        ),
    }


def test_preflight_reapplication_and_rollback_only_verification() -> None:
    apply_audit_prerequisites()
    run_sql_file(PREFLIGHT)
    run_sql_file(RETENTION_MIGRATION)
    run_sql_file(PREFLIGHT)
    before = retention_snapshot()

    run_sql_file(RETENTION_MIGRATION)
    assert retention_snapshot() == before

    run_sql_file(VERIFICATION)
    assert execute(
        """
        select count(*)
        from public.authentication_audit_events
        where id between
              '00000000-0000-4000-8000-000000001041'::uuid
              and '00000000-0000-4000-8000-000000001045'::uuid
        """,
        fetch=True,
    ) == [(0,)]


def test_expiry_boundary_oldest_first_batching_and_repeated_zero() -> None:
    apply_retention()
    event_ids = [str(uuid4()) for _ in range(5)]
    insert_event(event_ids[0], CUTOFF - timedelta(seconds=3))
    insert_event(event_ids[1], CUTOFF - timedelta(seconds=2))
    insert_event(event_ids[2], CUTOFF - timedelta(seconds=1))
    insert_event(event_ids[3], CUTOFF)
    insert_event(event_ids[4], CUTOFF + timedelta(seconds=1))

    assert cleanup_as("service_role", CUTOFF, 2) == 2
    assert execute(
        """
        select id::text
        from public.authentication_audit_events
        order by occurred_at, id
        """,
        fetch=True,
    ) == [(event_ids[2],), (event_ids[3],), (event_ids[4],)]

    assert cleanup_as("service_role", CUTOFF, 2) == 1
    assert cleanup_as("service_role", CUTOFF, 2) == 0
    assert execute(
        """
        select id::text, occurred_at
        from public.authentication_audit_events
        order by occurred_at, id
        """,
        fetch=True,
    ) == [
        (event_ids[3], CUTOFF),
        (event_ids[4], CUTOFF + timedelta(seconds=1)),
    ]


@pytest.mark.parametrize(
    ("cutoff_sql", "limit_sql"),
    [
        ("null", "1"),
        ("'infinity'::timestamptz", "1"),
        ("pg_catalog.now() + interval '1 day'", "1"),
        ("pg_catalog.now() - interval '180 days'", "null"),
        ("pg_catalog.now() - interval '180 days'", "0"),
        ("pg_catalog.now() - interval '180 days'", "1001"),
    ],
)
def test_invalid_cutoffs_and_limits_fail(
    cutoff_sql: str,
    limit_sql: str,
) -> None:
    apply_retention()

    with pytest.raises(psycopg.errors.InvalidParameterValue):
        execute_as(
            "service_role",
            (
                "select public.cleanup_authentication_audit_events("
                f"{cutoff_sql}, {limit_sql})"
            ),
        )


def test_exact_security_properties_acl_rls_and_role_enforcement() -> None:
    apply_retention()
    owner = execute("select current_user", fetch=True)[0][0]
    cleanup_function = (
        "public.cleanup_authentication_audit_events"
        "(timestamp with time zone,integer)"
    )

    assert execute(
        """
        select
            pg_catalog.pg_get_userbyid(function_definition.proowner),
            function_definition.prosecdef,
            function_definition.provolatile,
            function_definition.proparallel,
            function_definition.proleakproof,
            function_definition.proisstrict,
            function_definition.proconfig,
            pg_catalog.pg_get_function_identity_arguments(
                function_definition.oid
            ),
            pg_catalog.pg_get_function_result(function_definition.oid)
        from pg_catalog.pg_proc as function_definition
        where function_definition.oid =
              'public.cleanup_authentication_audit_events(timestamptz,integer)'::regprocedure
        """,
        fetch=True,
    ) == [
        (
            owner,
            True,
            "v",
            "u",
            False,
            False,
            ["search_path=pg_catalog"],
            "p_cutoff timestamp with time zone, p_batch_limit integer",
            "integer",
        )
    ]

    assert execute(
        """
        select
            coalesce(role_definition.rolname, 'PUBLIC'),
            privilege.privilege_type,
            privilege.is_grantable
        from pg_catalog.pg_proc as function_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                function_definition.proacl,
                pg_catalog.acldefault('f', function_definition.proowner)
            )
        ) as privilege
        left join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where function_definition.oid =
              'public.cleanup_authentication_audit_events(timestamptz,integer)'::regprocedure
        order by 1
        """,
        fetch=True,
    ) == sorted(
        [
            (owner, "EXECUTE", False),
            ("service_role", "EXECUTE", False),
        ]
    )

    assert execute(
        """
        select
            coalesce(role_definition.rolname, 'PUBLIC'),
            privilege.privilege_type,
            privilege.is_grantable
        from pg_catalog.pg_class as table_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                table_definition.relacl,
                pg_catalog.acldefault('r', table_definition.relowner)
            )
        ) as privilege
        left join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where table_definition.oid =
              'public.authentication_audit_events'::regclass
        order by 1, 2
        """,
        fetch=True,
    ) == sorted(
        [
            (owner, "DELETE", False),
            (owner, "INSERT", False),
            (owner, "SELECT", False),
            ("service_role", "SELECT", False),
        ]
    )

    assert execute(
        """
        select
            attribute_definition.attname,
            coalesce(role_definition.rolname, 'PUBLIC'),
            privilege.privilege_type,
            privilege.is_grantable
        from pg_catalog.pg_attribute as attribute_definition
        cross join lateral pg_catalog.aclexplode(
            attribute_definition.attacl
        ) as privilege
        left join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where attribute_definition.attrelid =
              'public.authentication_audit_events'::regclass
          and attribute_definition.attnum > 0
          and not attribute_definition.attisdropped
        order by 1, 2, 3
        """,
        fetch=True,
    ) == [("user_id", owner, "UPDATE", False)]

    assert execute(
        """
        select
            pg_catalog.pg_get_userbyid(table_definition.relowner),
            table_definition.relrowsecurity,
            table_definition.relforcerowsecurity,
            (
                select count(*)
                from pg_catalog.pg_policy as policy_definition
                where policy_definition.polrelid = table_definition.oid
            ),
            has_table_privilege(
                'service_role',
                table_definition.oid,
                'DELETE'
            ),
            has_function_privilege(
                'service_role',
                %s,
                'EXECUTE'
            ),
            has_function_privilege('anon', %s, 'EXECUTE'),
            has_function_privilege('authenticated', %s, 'EXECUTE'),
            has_table_privilege(
                %s,
                table_definition.oid,
                'DELETE'
            ),
            has_column_privilege(
                %s,
                table_definition.oid,
                'user_id',
                'UPDATE'
            )
        from pg_catalog.pg_class as table_definition
        where table_definition.oid =
              'public.authentication_audit_events'::regclass
        """,
        (
            cleanup_function,
            cleanup_function,
            cleanup_function,
            owner,
            owner,
        ),
        fetch=True,
    ) == [
        (
            owner,
            True,
            False,
            0,
            False,
            True,
            False,
            False,
            True,
            True,
        )
    ]

    assert cleanup_as("service_role", CUTOFF, 1) == 0
    for role in ("anon", "authenticated"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cleanup_as(role, CUTOFF, 1)

    insert_event(str(uuid4()), CUTOFF - timedelta(seconds=1))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        execute_as(
            "service_role",
            """
            delete from public.authentication_audit_events
            where occurred_at < %s
            """,
            (CUTOFF,),
        )


def test_non_superuser_definer_repairs_hosted_v1_owner_delete_acl() -> None:
    owner = "retention_acl_migrator"
    apply_audit_prerequisites_as_session(owner)

    migration_sql = RETENTION_MIGRATION.read_text(encoding="utf-8")
    owner_delete_grant = (
        "grant delete on table public.authentication_audit_events "
        "to current_user;\n"
    )
    assert migration_sql.count(owner_delete_grant) == 1
    hosted_v1_sql = migration_sql.replace(owner_delete_grant, "", 1)
    execute_as_session(owner, hosted_v1_sql)

    assert execute(
        """
        select
            pg_catalog.pg_get_userbyid(table_definition.relowner),
            pg_catalog.pg_get_userbyid(function_definition.proowner),
            function_definition.prosecdef,
            table_definition.relrowsecurity,
            table_definition.relforcerowsecurity,
            has_table_privilege(%s, table_definition.oid, 'SELECT'),
            has_table_privilege(%s, table_definition.oid, 'UPDATE'),
            has_column_privilege(
                %s,
                table_definition.oid,
                'user_id',
                'UPDATE'
            ),
            has_table_privilege(%s, table_definition.oid, 'DELETE'),
            has_table_privilege(
                'service_role',
                table_definition.oid,
                'SELECT'
            ),
            has_table_privilege(
                'service_role',
                table_definition.oid,
                'DELETE'
            ),
            has_function_privilege(
                'service_role',
                function_definition.oid,
                'EXECUTE'
            ),
            has_function_privilege(
                'anon',
                function_definition.oid,
                'EXECUTE'
            ),
            has_function_privilege(
                'authenticated',
                function_definition.oid,
                'EXECUTE'
            ),
            has_function_privilege(
                'public',
                function_definition.oid,
                'EXECUTE'
            )
        from pg_catalog.pg_class as table_definition
        cross join pg_catalog.pg_proc as function_definition
        where table_definition.oid =
              'public.authentication_audit_events'::regclass
          and function_definition.oid =
              'public.cleanup_authentication_audit_events(timestamptz,integer)'::regprocedure
        """,
        (owner, owner, owner, owner),
        fetch=True,
    ) == [
        (
            owner,
            owner,
            True,
            True,
            False,
            True,
            False,
            True,
            False,
            True,
            False,
            True,
            False,
            False,
            False,
        )
    ]
    assert execute(
        """
        select
            coalesce(role_definition.rolname, 'PUBLIC'),
            privilege.privilege_type,
            privilege.is_grantable
        from pg_catalog.pg_class as table_definition
        cross join lateral pg_catalog.aclexplode(
            table_definition.relacl
        ) as privilege
        left join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where table_definition.oid =
              'public.authentication_audit_events'::regclass
        order by 1, 2
        """,
        fetch=True,
    ) == sorted(
        [
            (owner, "INSERT", False),
            (owner, "SELECT", False),
            ("service_role", "SELECT", False),
        ]
    )
    assert execute(
        """
        select
            attribute_definition.attname,
            coalesce(role_definition.rolname, 'PUBLIC'),
            privilege.privilege_type,
            privilege.is_grantable
        from pg_catalog.pg_attribute as attribute_definition
        cross join lateral pg_catalog.aclexplode(
            attribute_definition.attacl
        ) as privilege
        left join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where attribute_definition.attrelid =
              'public.authentication_audit_events'::regclass
          and attribute_definition.attnum > 0
          and not attribute_definition.attisdropped
        order by 1, 2, 3
        """,
        fetch=True,
    ) == [("user_id", owner, "UPDATE", False)]

    event_ids = [str(uuid4()) for _ in range(5)]
    insert_event(event_ids[0], CUTOFF - timedelta(seconds=3))
    insert_event(event_ids[1], CUTOFF - timedelta(seconds=2))
    insert_event(event_ids[2], CUTOFF)
    insert_event(event_ids[3], CUTOFF + timedelta(seconds=1))

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cleanup_as("service_role", CUTOFF, 1)
    assert execute(
        """
        select count(*)
        from public.authentication_audit_events
        where id = any(%s::uuid[])
        """,
        (event_ids[:4],),
        fetch=True,
    ) == [(4,)]

    run_sql_file_as_session(owner, PREFLIGHT)
    run_sql_file_as_session(owner, RETENTION_MIGRATION)

    assert execute(
        """
        select
            has_table_privilege(
                %s,
                'public.authentication_audit_events',
                'DELETE'
            ),
            has_table_privilege(
                'service_role',
                'public.authentication_audit_events',
                'DELETE'
            )
        """,
        (owner,),
        fetch=True,
    ) == [(True, False)]
    assert cleanup_as("service_role", CUTOFF, 1) == 1
    assert execute(
        """
        select id::text
        from public.authentication_audit_events
        order by occurred_at, id
        """,
        fetch=True,
    ) == [
        (event_ids[1],),
        (event_ids[2],),
        (event_ids[3],),
    ]

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        execute_as(
            "service_role",
            """
            delete from public.authentication_audit_events
            where occurred_at < %s
            """,
            (CUTOFF,),
        )
    for role in ("anon", "authenticated"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cleanup_as(role, CUTOFF, 1)

    insert_event(event_ids[4], CUTOFF - timedelta(seconds=1))
    execute(
        """
        create function public.reject_retention_acl_regression_delete()
        returns trigger
        language plpgsql
        as $$
        begin
            raise exception 'synthetic retention ACL rollback';
        end;
        $$;
        create trigger reject_retention_acl_regression_delete
        before delete on public.authentication_audit_events
        for each statement
        execute function public.reject_retention_acl_regression_delete();
        """,
    )
    with pytest.raises(
        psycopg.errors.RaiseException,
        match="synthetic retention ACL rollback",
    ):
        cleanup_as("service_role", CUTOFF, 1000)
    assert execute(
        """
        select id::text
        from public.authentication_audit_events
        where id in (%s, %s)
        order by occurred_at, id
        """,
        (event_ids[1], event_ids[4]),
        fetch=True,
    ) == [(event_ids[1],), (event_ids[4],)]

    execute(
        """
        drop trigger reject_retention_acl_regression_delete
            on public.authentication_audit_events;
        drop function public.reject_retention_acl_regression_delete();
        """,
    )
    assert cleanup_as("service_role", CUTOFF, 1000) == 2
    assert cleanup_as("service_role", CUTOFF, 1000) == 0
    assert execute(
        """
        select id::text
        from public.authentication_audit_events
        order by occurred_at, id
        """,
        fetch=True,
    ) == [(event_ids[2],), (event_ids[3],)]

    run_sql_file_as_session(owner, VERIFICATION)


def test_late_migration_failure_rolls_back_function_creation_and_acl() -> None:
    apply_audit_prerequisites()
    migration_sql = RETENTION_MIGRATION.read_text(encoding="utf-8")
    assert migration_sql.rstrip().endswith("commit;")
    failing_sql = migration_sql.rsplit("commit;", maxsplit=1)[0] + (
        "select 1 / 0;\ncommit;\n"
    )

    with pytest.raises(psycopg.errors.DivisionByZero):
        execute(failing_sql)

    assert execute(
        """
        select
            to_regprocedure(
                'public.cleanup_authentication_audit_events(timestamptz,integer)'
            ),
            exists (
                select 1
                from pg_catalog.pg_class as table_definition
                cross join lateral pg_catalog.aclexplode(
                    table_definition.relacl
                ) as privilege
                where table_definition.oid =
                      'public.authentication_audit_events'::regclass
                  and privilege.grantee = to_regrole(current_user)
                  and privilege.privilege_type = 'DELETE'
            )
        """,
        fetch=True,
    ) == [(None, False)]


def test_failed_delete_statement_preserves_all_existing_rows_for_retry() -> None:
    apply_retention()
    event_ids = [str(uuid4()), str(uuid4())]
    insert_event(event_ids[0], CUTOFF - timedelta(seconds=2))
    insert_event(event_ids[1], CUTOFF - timedelta(seconds=1))
    execute(
        """
        create function public.reject_authentication_audit_delete()
        returns trigger
        language plpgsql
        as $$
        begin
            raise exception 'synthetic cleanup failure';
        end;
        $$;
        create trigger reject_authentication_audit_delete
        before delete on public.authentication_audit_events
        for each statement
        execute function public.reject_authentication_audit_delete();
        """
    )

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="synthetic cleanup failure",
    ):
        cleanup_as("service_role", CUTOFF, 2)

    assert execute(
        """
        select id::text
        from public.authentication_audit_events
        order by occurred_at, id
        """,
        fetch=True,
    ) == [(event_ids[0],), (event_ids[1],)]

    execute(
        """
        drop trigger reject_authentication_audit_delete
        on public.authentication_audit_events
        """
    )
    assert cleanup_as("service_role", CUTOFF, 2) == 2


def test_fresh_schema_and_sequential_migrations_have_equivalent_retention_objects() -> None:
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
        """
    )
    run_sql_file(SCHEMA)
    fresh_snapshot = retention_snapshot()

    execute(
        """
        drop schema public cascade;
        create schema public;
        grant usage on schema public to service_role, anon, authenticated;
        create table public.users (
            id uuid primary key,
            email text,
            name text not null
        );
        """
    )
    apply_retention()
    sequential_snapshot = retention_snapshot()

    assert fresh_snapshot == sequential_snapshot


def test_occurred_at_index_supports_cutoff_candidate_scan() -> None:
    apply_retention()

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("set enable_seqscan = off")
            cursor.execute(
                """
                explain (costs off)
                select id
                from public.authentication_audit_events
                where occurred_at < %s
                order by occurred_at asc, id asc
                limit 1000
                """,
                (CUTOFF,),
            )
            plan = cursor.fetchall()
    rendered = "\n".join(row[0] for row in plan)

    assert "idx_authentication_audit_events_occurred_at" in rendered
    assert execute(
        """
        select
            index_definition.indisvalid,
            index_definition.indisready,
            index_definition.indislive,
            pg_catalog.pg_get_indexdef(
                index_definition.indexrelid,
                1,
                true
            )
        from pg_catalog.pg_index as index_definition
        where index_definition.indexrelid =
              'public.idx_authentication_audit_events_occurred_at'::regclass
        """,
        fetch=True,
    ) == [(True, True, True, "occurred_at")]


def test_record_rpc_behavior_is_unchanged_after_retention_migration() -> None:
    apply_retention()
    event_id = str(uuid4())
    params = (
        event_id,
        "login",
        "succeeded",
        "password",
        None,
        None,
        None,
        "retention-regression",
        "test",
    )
    sql = """
        select public.record_authentication_audit_event(
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """

    assert execute_as("service_role", sql, params, fetch=True) == [(True,)]
    assert execute_as("service_role", sql, params, fetch=True) == [(False,)]
    assert cleanup_as("service_role", CUTOFF, 1000) == 0
    assert execute(
        """
        select count(*)
        from public.authentication_audit_events
        where id = %s
        """,
        (event_id,),
        fetch=True,
    ) == [(1,)]


def test_preflight_rejects_unexpected_overload_and_unrelated_owner() -> None:
    apply_audit_prerequisites()
    execute(
        """
        create function public.cleanup_authentication_audit_events(
            p_cutoff timestamptz
        )
        returns integer
        language sql
        as 'select 0';
        """
    )
    with pytest.raises(
        psycopg.errors.InsufficientPrivilege,
        match="overload",
    ):
        run_sql_file(PREFLIGHT)

    execute(
        """
        drop function public.cleanup_authentication_audit_events(timestamptz);
        create function public.cleanup_authentication_audit_events(
            p_cutoff timestamptz,
            p_batch_limit integer
        )
        returns integer
        language sql
        as 'select 0';
        alter function public.cleanup_authentication_audit_events(
            timestamptz, integer
        ) owner to retention_rogue;
        """
    )
    with pytest.raises(
        psycopg.errors.InsufficientPrivilege,
        match="owner",
    ):
        run_sql_file(PREFLIGHT)
