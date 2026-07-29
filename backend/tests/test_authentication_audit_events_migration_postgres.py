"""Real PostgreSQL checks for ISSUE-1031 authentication audit persistence.

Set AUTHENTICATION_AUDIT_DATABASE_URL to a disposable database. These tests
destroy and recreate the public schema and must never target a shared database.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
import pytest

from app.services.account_deletion import _validated_delete_account_response

DATABASE_URL = os.getenv("AUTHENTICATION_AUDIT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="AUTHENTICATION_AUDIT_DATABASE_URL is not configured",
)
BACKEND_DIR = Path(__file__).parents[1]
MIGRATION = BACKEND_DIR / "migrations" / "authentication_audit_events.sql"
PHASE_2_MIGRATION = (
    BACKEND_DIR / "migrations" / "authentication_audit_revocation_phase_2.sql"
)
PREFLIGHT = (
    BACKEND_DIR / "scripts" / "authentication_audit_events_migration_preflight.sql"
)
VERIFICATION = (
    BACKEND_DIR / "scripts" / "verify_authentication_audit_events_migration.sql"
)
SCHEMA = BACKEND_DIR / "schema.sql"


def execute(sql: str, params: tuple = (), *, fetch: bool = False):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params if params else None)
            return cursor.fetchall() if fetch else None


def execute_as(role: str, sql: str, params: tuple = (), *, fetch: bool = False):
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
            create role authentication_audit_migrator nologin noinherit;
        exception when duplicate_object then null;
        end
        $$;
        do $$
        begin
            create role rogue_auth_role nologin bypassrls;
        exception when duplicate_object then null;
        end
        $$;
        alter role service_role bypassrls;
        alter role rogue_auth_role bypassrls;
        grant usage on schema public to service_role, anon, authenticated;
        grant usage, create on schema public to authentication_audit_migrator;
        alter role authentication_audit_migrator noinherit;
        do $$
        begin
            if current_setting('server_version_num')::integer >= 160000 then
                execute
                    'grant service_role to authentication_audit_migrator '
                    'with set true';
            else
                execute
                    'grant service_role to authentication_audit_migrator';
            end if;
        end
        $$;
        create table public.users (
            id uuid primary key,
            email text,
            name text not null
        );
        grant select, insert, update, delete, references
        on table public.users to authentication_audit_migrator;
        """
    )


def apply_migration() -> None:
    run_sql_file(MIGRATION)
    run_sql_file(PHASE_2_MIGRATION)


def apply_migration_as_session(role: str) -> None:
    run_sql_file_as_session(role, MIGRATION)
    run_sql_file_as_session(role, PHASE_2_MIGRATION)


def reset_public_for_full_schema() -> None:
    execute(
        """
        drop schema if exists public cascade;
        create schema public;
        """
    )


def reset_public_for_audit_migrations() -> None:
    execute(
        """
        drop schema if exists public cascade;
        create schema public;
        grant usage on schema public to service_role, anon, authenticated;
        grant usage, create on schema public to authentication_audit_migrator;
        create table public.users (
            id uuid primary key,
            email text,
            name text not null
        );
        grant select, insert, update, delete, references
        on table public.users to authentication_audit_migrator;
        """
    )


def audit_object_snapshot() -> dict[str, list[tuple]]:
    return {
        "table": execute(
            """
            select
                pg_catalog.pg_get_userbyid(relowner),
                relrowsecurity,
                relforcerowsecurity
            from pg_catalog.pg_class
            where oid='public.authentication_audit_events'::regclass
            """,
            fetch=True,
        ),
        "columns": execute(
            """
            select
                attribute_definition.attnum,
                attribute_definition.attname,
                pg_catalog.format_type(
                    attribute_definition.atttypid,
                    attribute_definition.atttypmod
                ),
                attribute_definition.attnotnull,
                pg_catalog.pg_get_expr(
                    default_definition.adbin,
                    default_definition.adrelid
                )
            from pg_catalog.pg_attribute as attribute_definition
            left join pg_catalog.pg_attrdef as default_definition
              on default_definition.adrelid=attribute_definition.attrelid
             and default_definition.adnum=attribute_definition.attnum
            where attribute_definition.attrelid =
                  'public.authentication_audit_events'::regclass
              and attribute_definition.attnum > 0
              and not attribute_definition.attisdropped
            order by attribute_definition.attnum
            """,
            fetch=True,
        ),
        "constraints": execute(
            """
            select
                constraint_definition.conname,
                constraint_definition.contype,
                pg_catalog.pg_get_constraintdef(
                    constraint_definition.oid,
                    true
                )
            from pg_catalog.pg_constraint as constraint_definition
            where constraint_definition.conrelid =
                  'public.authentication_audit_events'::regclass
            order by constraint_definition.conname
            """,
            fetch=True,
        ),
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
                pg_catalog.pg_get_functiondef(function_definition.oid)
            from pg_catalog.pg_proc as function_definition
            where function_definition.oid =
                  'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'::regprocedure
            """,
            fetch=True,
        ),
        "indexes": execute(
            """
            select
                index_definition.relname,
                pg_catalog.pg_get_indexdef(index_catalog.indexrelid),
                index_catalog.indisvalid,
                index_catalog.indisready,
                index_catalog.indislive
            from pg_catalog.pg_index as index_catalog
            join pg_catalog.pg_class as index_definition
              on index_definition.oid=index_catalog.indexrelid
            where index_catalog.indrelid =
                  'public.authentication_audit_events'::regclass
            order by index_definition.relname
            """,
            fetch=True,
        ),
        "policies": execute(
            """
            select
                policy_definition.polname,
                policy_definition.polcmd,
                policy_definition.polpermissive,
                policy_definition.polroles,
                pg_catalog.pg_get_expr(
                    policy_definition.polqual,
                    policy_definition.polrelid
                ),
                pg_catalog.pg_get_expr(
                    policy_definition.polwithcheck,
                    policy_definition.polrelid
                )
            from pg_catalog.pg_policy as policy_definition
            where policy_definition.polrelid =
                  'public.authentication_audit_events'::regclass
            order by policy_definition.polname
            """,
            fetch=True,
        ),
        "direct_acls": direct_audit_acl_rows(),
    }


def add_user(user_id: str | None = None) -> str:
    selected_id = user_id or str(uuid4())
    execute(
        "insert into public.users(id,email,name) values (%s,%s,'Audit User')",
        (selected_id, f"{selected_id}@example.invalid"),
    )
    return selected_id


def rpc_params(
    *,
    event_id: str | None = None,
    event_type: str = "login",
    outcome: str = "succeeded",
    auth_method: str = "password",
    user_id: str | None = None,
    failure_category: str | None = None,
    revocation_reason: str | None = None,
    correlation_id: str = "correlation-1031",
    source_environment: str = "test",
) -> tuple:
    return (
        event_id or str(uuid4()),
        event_type,
        outcome,
        auth_method,
        user_id,
        failure_category,
        revocation_reason,
        correlation_id,
        source_environment,
    )


RPC_SQL = """
select public.record_authentication_audit_event(
    %s,%s,%s,%s,%s,%s,%s,%s,%s
)
"""


def direct_audit_acl_rows() -> list[tuple]:
    return execute(
        """
        with direct_acl as (
            select
                'table'::text as object_kind,
                privilege.grantee,
                privilege.privilege_type,
                privilege.is_grantable
            from pg_catalog.pg_class as table_definition
            cross join lateral pg_catalog.aclexplode(
                coalesce(
                    table_definition.relacl,
                    pg_catalog.acldefault('r', table_definition.relowner)
                )
            ) as privilege
            where table_definition.oid =
                  'public.authentication_audit_events'::regclass

            union all

            select
                'column:' || attribute_definition.attname,
                privilege.grantee,
                privilege.privilege_type,
                privilege.is_grantable
            from pg_catalog.pg_attribute as attribute_definition
            cross join lateral pg_catalog.aclexplode(
                attribute_definition.attacl
            ) as privilege
            where attribute_definition.attrelid =
                  'public.authentication_audit_events'::regclass
              and attribute_definition.attnum > 0
              and not attribute_definition.attisdropped

            union all

            select
                'function'::text,
                privilege.grantee,
                privilege.privilege_type,
                privilege.is_grantable
            from pg_catalog.pg_proc as function_definition
            cross join lateral pg_catalog.aclexplode(
                coalesce(
                    function_definition.proacl,
                    pg_catalog.acldefault('f', function_definition.proowner)
                )
            ) as privilege
            where function_definition.oid =
                  'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'::regprocedure
        )
        select
            direct_acl.object_kind,
            coalesce(role_definition.rolname, 'PUBLIC'),
            direct_acl.privilege_type,
            direct_acl.is_grantable
        from direct_acl
        left join pg_catalog.pg_roles as role_definition
          on role_definition.oid = direct_acl.grantee
        order by
            direct_acl.object_kind,
            coalesce(role_definition.rolname, 'PUBLIC'),
            direct_acl.privilege_type
        """,
        fetch=True,
    )


def test_preflight_and_rollback_only_verification() -> None:
    run_sql_file(PREFLIGHT)
    apply_migration()
    run_sql_file(PREFLIGHT)
    apply_migration()
    run_sql_file(VERIFICATION)
    assert execute(
        """
        select
            count(*),
            to_regclass('public.authentication_audit_events_expected') is null
        from public.authentication_audit_events
        """,
        fetch=True,
    ) == [(0, True)]


def test_fresh_schema_and_sequential_migrations_have_equivalent_audit_objects() -> None:
    reset_public_for_full_schema()
    run_sql_file(SCHEMA)
    fresh_snapshot = audit_object_snapshot()

    reset_public_for_audit_migrations()
    apply_migration()
    sequential_snapshot = audit_object_snapshot()

    assert fresh_snapshot == sequential_snapshot


def test_phase_2_reapplication_is_exactly_idempotent() -> None:
    run_sql_file(MIGRATION)
    run_sql_file(PHASE_2_MIGRATION)
    before = audit_object_snapshot()

    run_sql_file(PHASE_2_MIGRATION)

    assert audit_object_snapshot() == before


def test_phase_2_late_failure_restores_pre_phase_2_catalog_and_acls() -> None:
    run_sql_file(MIGRATION)
    before = audit_object_snapshot()
    migration_sql = PHASE_2_MIGRATION.read_text(encoding="utf-8")
    failing_sql = migration_sql.rsplit("commit;", maxsplit=1)[0] + (
        "select 1 / 0;\ncommit;\n"
    )

    with pytest.raises(psycopg.errors.DivisionByZero):
        execute(failing_sql)

    assert audit_object_snapshot() == before


def test_fresh_schema_account_deletion_and_post_delete_audit_row() -> None:
    reset_public_for_full_schema()
    run_sql_file(SCHEMA)
    user_id = str(uuid4())
    execute(
        """
        insert into public.users(id,email,name)
        values (%s,%s,'Fresh Schema Delete')
        """,
        (user_id, f"{user_id}@example.invalid"),
    )

    rpc_rows = execute_as(
        "service_role",
        "select public.delete_user_account(%s)",
        (user_id,),
        fetch=True,
    )
    parsed = _validated_delete_account_response(
        SimpleNamespace(data=rpc_rows[0][0])
    )
    assert parsed == {"deleted": True, "games_reconciled": 0}
    assert execute(
        "select count(*) from public.users where id=%s",
        (user_id,),
        fetch=True,
    ) == [(0,)]

    event_id = str(uuid4())
    assert execute_as(
        "service_role",
        RPC_SQL,
        rpc_params(
            event_id=event_id,
            event_type="token_revocation",
            outcome="succeeded",
            auth_method="password",
            user_id=None,
            revocation_reason="account_deleted",
            correlation_id="fresh-delete-correlation",
        ),
        fetch=True,
    ) == [(True,)]
    assert execute(
        """
        select revocation_reason, auth_method, user_id
        from public.authentication_audit_events
        where id=%s
        """,
        (event_id,),
        fetch=True,
    ) == [("account_deleted", "password", None)]


def test_supported_fresh_migration_runs_as_non_superuser_owner() -> None:
    run_sql_file_as_session("authentication_audit_migrator", PREFLIGHT)
    apply_migration_as_session("authentication_audit_migrator")
    run_sql_file_as_session("authentication_audit_migrator", VERIFICATION)
    owner_rpc_event_id = str(uuid4())
    service_rpc_event_id = str(uuid4())

    assert execute(
        """
        select
            pg_get_userbyid(table_definition.relowner),
            pg_get_userbyid(function_definition.proowner)
        from pg_catalog.pg_class as table_definition
        cross join pg_catalog.pg_proc as function_definition
        where table_definition.oid =
              'public.authentication_audit_events'::regclass
          and function_definition.oid =
              'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'::regprocedure
        """,
        fetch=True,
    ) == [("authentication_audit_migrator", "authentication_audit_migrator")]
    assert execute_as_session(
        "authentication_audit_migrator",
        RPC_SQL,
        rpc_params(event_id=owner_rpc_event_id),
        fetch=True,
    ) == [(True,)]
    assert execute_as(
        "service_role",
        RPC_SQL,
        rpc_params(event_id=service_rpc_event_id),
        fetch=True,
    ) == [(True,)]
    assert execute_as_session(
        "authentication_audit_migrator",
        """
        select id
        from public.authentication_audit_events
        where id in (%s, %s)
        order by id
        """,
        (owner_rpc_event_id, service_rpc_event_id),
        fetch=True,
    ) == sorted(
        [(UUID(owner_rpc_event_id),), (UUID(service_rpc_event_id),)]
    )
    assert execute(
        """
        select
            has_table_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'SELECT'
            ),
            has_table_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'INSERT'
            ),
            has_table_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'UPDATE'
            ),
            has_table_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'DELETE'
            ),
            has_function_privilege(
                'authentication_audit_migrator',
                'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)',
                'EXECUTE'
            ),
            has_column_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'user_id',
                'UPDATE'
            ),
            has_column_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'source_environment',
                'UPDATE'
            )
        """,
        fetch=True,
    ) == [(True, True, False, False, True, True, False)]

    with pytest.raises(psycopg.errors.InsufficientPrivilege) as denied:
        execute_as_session(
            "authentication_audit_migrator",
            """
            update public.authentication_audit_events
            set source_environment = 'changed'
            where id = %s
            """,
            (owner_rpc_event_id,),
        )
    assert denied.value.sqlstate == "42501"


def test_fk_set_null_requires_only_owner_user_id_column_update() -> None:
    apply_migration_as_session("authentication_audit_migrator")
    execute_as_session(
        "authentication_audit_migrator",
        """
        create function public.delete_authentication_audit_test_user(
            p_user_id uuid
        )
        returns boolean
        language plpgsql
        security definer
        set search_path = pg_catalog
        as $$
        begin
            delete from public.users where id = p_user_id;
            return found;
        end;
        $$;
        revoke all on function public.delete_authentication_audit_test_user(uuid)
            from public, anon, authenticated;
        grant execute on function
            public.delete_authentication_audit_test_user(uuid)
            to service_role;
        """,
    )
    user_id = add_user()
    event_id = str(uuid4())
    assert execute_as(
        "service_role",
        RPC_SQL,
        rpc_params(event_id=event_id, user_id=user_id),
        fetch=True,
    ) == [(True,)]

    # Reproduce the pre-fix hosted-like privilege model. service_role invokes a
    # SECURITY DEFINER user-deletion function owned by the same non-superuser
    # trusted role as the audit RPC and table.
    execute_as_session(
        "authentication_audit_migrator",
        """
        revoke update (user_id)
            on public.authentication_audit_events
            from current_user
        """,
    )
    assert execute(
        """
        select
            has_schema_privilege(
                'authentication_audit_migrator',
                'public',
                'USAGE'
            ),
            has_table_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'SELECT'
            ),
            has_table_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'INSERT'
            ),
            has_table_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'UPDATE'
            ),
            has_column_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'user_id',
                'UPDATE'
            ),
            has_table_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'DELETE'
            )
        """,
        fetch=True,
    ) == [(True, True, True, False, False, False)]

    with pytest.raises(psycopg.errors.InsufficientPrivilege) as denied:
        execute_as(
            "service_role",
            """
            select public.delete_authentication_audit_test_user(%s)
            """,
            (user_id,),
            fetch=True,
        )
    assert denied.value.sqlstate == "42501"
    privilege_context = denied.value.diag.context or ""
    assert 'UPDATE ONLY "public"."authentication_audit_events"' in privilege_context
    assert '"user_id" = NULL' in privilege_context
    assert execute(
        "select count(*) from public.users where id = %s",
        (user_id,),
        fetch=True,
    ) == [(1,)]
    assert execute(
        """
        select user_id
        from public.authentication_audit_events
        where id = %s
        """,
        (event_id,),
        fetch=True,
    ) == [(UUID(user_id),)]

    execute_as_session(
        "authentication_audit_migrator",
        """
        grant update (user_id)
            on public.authentication_audit_events
            to current_user
        """,
    )
    assert execute(
        """
        select
            has_table_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'UPDATE'
            ),
            has_column_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'user_id',
                'UPDATE'
            ),
            has_column_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'source_environment',
                'UPDATE'
            ),
            has_table_privilege(
                'authentication_audit_migrator',
                'public.authentication_audit_events',
                'DELETE'
            )
        """,
        fetch=True,
    ) == [(False, True, False, False)]
    assert execute_as(
        "service_role",
        """
        select public.delete_authentication_audit_test_user(%s)
        """,
        (user_id,),
        fetch=True,
    ) == [(True,)]
    assert execute(
        """
        select user_id
        from public.authentication_audit_events
        where id = %s
        """,
        (event_id,),
        fetch=True,
    ) == [(None,)]


def test_non_superuser_without_service_role_authorization_is_rejected() -> None:
    execute("revoke service_role from authentication_audit_migrator")

    for path in (PREFLIGHT, MIGRATION):
        with pytest.raises(
            psycopg.errors.InsufficientPrivilege,
            match="SET ROLE service_role",
        ):
            run_sql_file_as_session("authentication_audit_migrator", path)

    assert execute(
        """
        select
            to_regclass('public.authentication_audit_events'),
            to_regprocedure(
                'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'
            )
        """,
        fetch=True,
    ) == [(None, None)]


def test_postgres_16_membership_without_set_authorization_is_rejected() -> None:
    server_version = int(execute("show server_version_num", fetch=True)[0][0])
    if server_version < 160000:
        pytest.skip("membership SET option was introduced in PostgreSQL 16")

    execute(
        """
        grant service_role to authentication_audit_migrator
        with set false
        """
    )

    for path in (PREFLIGHT, MIGRATION):
        with pytest.raises(
            psycopg.errors.InsufficientPrivilege,
            match="SET ROLE service_role",
        ):
            run_sql_file_as_session("authentication_audit_migrator", path)

    assert execute(
        """
        select
            to_regclass('public.authentication_audit_events'),
            to_regprocedure(
                'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'
            )
        """,
        fetch=True,
    ) == [(None, None)]


def test_preflight_rejects_partial_migration_state() -> None:
    execute(
        """
        create table public.authentication_audit_events (
            id uuid primary key
        )
        """
    )

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="partial migration state",
    ):
        run_sql_file(PREFLIGHT)


def test_missing_referenced_role_leaves_no_partial_objects() -> None:
    execute("revoke usage on schema public from anon")
    execute("drop role anon")

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="requires anon, authenticated, and service_role roles",
    ):
        apply_migration()

    assert execute(
        """
        select
            to_regclass('public.authentication_audit_events'),
            to_regprocedure(
                'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'
            ),
            to_regclass('public.idx_authentication_audit_events_occurred_at')
        """,
        fetch=True,
    ) == [(None, None, None)]


def test_injected_late_failure_rolls_back_all_core_objects() -> None:
    migration_sql = MIGRATION.read_text(encoding="utf-8")
    assert migration_sql.rstrip().endswith("commit;")
    failing_sql = migration_sql.rsplit("commit;", maxsplit=1)[0] + (
        "select 1 / 0;\ncommit;\n"
    )

    with pytest.raises(psycopg.errors.DivisionByZero):
        execute(failing_sql)

    assert execute(
        """
        select
            to_regclass('public.authentication_audit_events'),
            to_regprocedure(
                'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'
            ),
            to_regclass('public.idx_authentication_audit_events_occurred_at'),
            to_regclass(
                'public.idx_authentication_audit_events_type_outcome_occurred_at'
            ),
            to_regclass('public.idx_authentication_audit_events_user_occurred_at')
        """,
        fetch=True,
    ) == [(None, None, None, None, None)]


def test_injected_late_failure_restores_all_preexisting_security_state() -> None:
    apply_migration_as_session("authentication_audit_migrator")
    execute_as_session(
        "authentication_audit_migrator",
        """
        alter table public.authentication_audit_events disable row level security;
        grant insert on public.authentication_audit_events to anon;
        grant update (outcome)
            on public.authentication_audit_events to authenticated;
        grant execute on function public.record_authentication_audit_event(
            uuid,text,text,text,uuid,text,text,text,text
        ) to anon;
        drop index public.idx_authentication_audit_events_occurred_at;
        """
    )
    before = audit_object_snapshot()
    migration_sql = MIGRATION.read_text(encoding="utf-8")
    failing_sql = migration_sql.rsplit("commit;", maxsplit=1)[0] + (
        "select 1 / 0;\ncommit;\n"
    )

    with pytest.raises(psycopg.errors.DivisionByZero):
        execute_as_session("authentication_audit_migrator", failing_sql)

    assert audit_object_snapshot() == before


@pytest.mark.parametrize(
    "hostile_sql",
    [
        """
        alter table public.authentication_audit_events add column metadata jsonb;
        grant select (metadata)
            on public.authentication_audit_events to anon
        """,
        """
        alter table public.authentication_audit_events
        drop column source_environment
        """,
        """
        alter table public.authentication_audit_events
        alter column source_environment type varchar(32)
        """,
        """
        alter table public.authentication_audit_events
        alter column source_environment drop not null
        """,
        """
        alter table public.authentication_audit_events
        alter column occurred_at drop default
        """,
        """
        alter table public.authentication_audit_events
        alter column id set default gen_random_uuid()
        """,
        """
        alter table public.authentication_audit_events
        drop constraint authentication_audit_events_event_type_check;
        alter table public.authentication_audit_events
        add constraint authentication_audit_events_event_type_check check (true)
        """,
        """
        alter table public.authentication_audit_events
        add constraint authentication_audit_events_unapproved_check
        check (char_length(source_environment) > 0)
        """,
        """
        alter table public.authentication_audit_events
        drop constraint authentication_audit_events_source_environment_check
        """,
        """
        drop index public.idx_authentication_audit_events_occurred_at;
        create index idx_authentication_audit_events_occurred_at
        on public.authentication_audit_events(auth_method)
        """,
        """
        drop index public.idx_authentication_audit_events_occurred_at;
        drop index public.idx_authentication_audit_events_type_outcome_occurred_at;
        create index idx_authentication_audit_events_occurred_at
        on public.authentication_audit_events(event_type, outcome, occurred_at desc);
        create index idx_authentication_audit_events_type_outcome_occurred_at
        on public.authentication_audit_events(occurred_at desc)
        """,
        """
        create index idx_authentication_audit_events_unapproved
        on public.authentication_audit_events(auth_method)
        """,
        """
        alter table public.authentication_audit_events
        drop constraint authentication_audit_events_pkey;
        create unique index authentication_audit_events_pkey
        on public.authentication_audit_events(id)
        """,
        """
        alter table public.authentication_audit_events
        drop constraint authentication_audit_events_user_id_fkey;
        alter table public.authentication_audit_events
        add constraint authentication_audit_events_user_id_fkey
        foreign key (user_id) references public.users(id) on delete cascade
        """,
        """
        create function public.record_authentication_audit_event(p_event_id uuid)
        returns boolean
        language sql
        as 'select true'
        """,
    ],
    ids=[
        "extra-metadata-json",
        "missing-column",
        "wrong-column-type",
        "wrong-nullability",
        "missing-occurred-at-default",
        "database-id-default",
        "dummy-check",
        "extra-check",
        "missing-check",
        "wrong-index",
        "swapped-index-names",
        "extra-index",
        "unique-not-primary",
        "wrong-fk-delete",
        "unexpected-rpc-overload",
    ],
)
def test_verification_rejects_hostile_complete_schema(hostile_sql: str) -> None:
    apply_migration()
    execute(hostile_sql)
    if "create function public.record_authentication_audit_event" in hostile_sql:
        with pytest.raises(
            psycopg.errors.InsufficientPrivilege,
            match="unexpected RPC overload",
        ):
            run_sql_file(PREFLIGHT)
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="authentication audit verification failed",
        ):
            run_sql_file(VERIFICATION)
        return

    run_sql_file(PREFLIGHT)
    apply_migration()

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="authentication audit verification failed",
    ):
        run_sql_file(VERIFICATION)


@pytest.mark.parametrize("health_column", ["indisvalid", "indisready", "indislive"])
def test_verification_rejects_unhealthy_approved_index(
    health_column: str,
) -> None:
    apply_migration()
    execute(
        f"""
        update pg_catalog.pg_index
        set {health_column} = false
        where indexrelid =
              'public.idx_authentication_audit_events_occurred_at'::regclass
        """
    )

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="authentication audit verification failed",
    ):
        run_sql_file(VERIFICATION)


def test_verification_rejects_missing_approved_index_before_repair() -> None:
    apply_migration()
    execute("drop index public.idx_authentication_audit_events_occurred_at")

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="authentication audit verification failed",
    ):
        run_sql_file(VERIFICATION)

    apply_migration()
    run_sql_file(VERIFICATION)


@pytest.mark.parametrize(
    "hostile_function_sql",
    [
        """
        alter function public.record_authentication_audit_event(
            uuid,text,text,text,uuid,text,text,text,text
        ) security invoker
        """,
        """
        alter function public.record_authentication_audit_event(
            uuid,text,text,text,uuid,text,text,text,text
        ) stable
        """,
        """
        alter function public.record_authentication_audit_event(
            uuid,text,text,text,uuid,text,text,text,text
        ) parallel safe
        """,
        """
        alter function public.record_authentication_audit_event(
            uuid,text,text,text,uuid,text,text,text,text
        ) reset search_path
        """,
    ],
)
def test_verification_rejects_hostile_rpc_properties(
    hostile_function_sql: str,
) -> None:
    apply_migration()
    execute(hostile_function_sql)

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="authentication audit verification failed",
    ):
        run_sql_file(VERIFICATION)


def test_unrelated_owners_are_rejected_without_changing_existing_state() -> None:
    apply_migration()
    execute(
        """
        alter table public.authentication_audit_events owner to rogue_auth_role;
        alter function public.record_authentication_audit_event(
            uuid,text,text,text,uuid,text,text,text,text
        ) owner to rogue_auth_role;
        """
    )
    before = execute(
        """
        select
            table_definition.relowner,
            table_definition.relacl::text,
            function_definition.proowner,
            function_definition.proacl::text
        from pg_catalog.pg_class as table_definition
        cross join pg_catalog.pg_proc as function_definition
        where table_definition.oid =
              'public.authentication_audit_events'::regclass
          and function_definition.oid =
              'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'::regprocedure
        """,
        fetch=True,
    )

    for path in (PREFLIGHT, MIGRATION):
        with pytest.raises(
            psycopg.errors.InsufficientPrivilege,
            match="owned by an unrelated role",
        ):
            run_sql_file_as_session("authentication_audit_migrator", path)

    after = execute(
        """
        select
            table_definition.relowner,
            table_definition.relacl::text,
            function_definition.proowner,
            function_definition.proacl::text
        from pg_catalog.pg_class as table_definition
        cross join pg_catalog.pg_proc as function_definition
        where table_definition.oid =
              'public.authentication_audit_events'::regclass
          and function_definition.oid =
              'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'::regprocedure
        """,
        fetch=True,
    )
    assert after == before


def test_verification_accepts_system_effective_privileges_without_direct_acl() -> None:
    apply_migration()
    migration_owner = execute("select current_user", fetch=True)[0][0]
    execute(
        """
        drop role if exists authentication_audit_test_superuser;
        drop role if exists supabase_audit_test_system_role;
        drop role if exists supabase_read_only_user;
        create role authentication_audit_test_superuser nologin superuser;
        create role supabase_audit_test_system_role nologin bypassrls;
        create role supabase_read_only_user nologin;
        grant pg_read_all_data to supabase_audit_test_system_role;
        grant pg_read_all_data to supabase_read_only_user;
        """
    )
    try:
        assert execute(
            """
            select
                has_table_privilege(
                    'authentication_audit_test_superuser',
                    'public.authentication_audit_events',
                    'DELETE'
                ),
                has_function_privilege(
                    'authentication_audit_test_superuser',
                    'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)',
                    'EXECUTE'
                ),
                has_table_privilege(
                    'pg_read_all_data',
                    'public.authentication_audit_events',
                    'SELECT'
                ),
                has_table_privilege(
                    'pg_write_all_data',
                    'public.authentication_audit_events',
                    'INSERT'
                ),
                has_table_privilege(
                    'supabase_audit_test_system_role',
                    'public.authentication_audit_events',
                    'SELECT'
                ),
                has_table_privilege(
                    'supabase_read_only_user',
                    'public.authentication_audit_events',
                    'SELECT'
                )
            """,
            fetch=True,
        ) == [(True, True, True, True, True, True)]
        assert direct_audit_acl_rows() == sorted(
            [
                ("column:user_id", migration_owner, "UPDATE", False),
                ("function", migration_owner, "EXECUTE", False),
                ("function", "service_role", "EXECUTE", False),
                ("table", migration_owner, "INSERT", False),
                ("table", migration_owner, "SELECT", False),
                ("table", "service_role", "SELECT", False),
            ]
        )

        run_sql_file(VERIFICATION)
    finally:
        execute(
            """
            revoke pg_read_all_data from supabase_audit_test_system_role;
            revoke pg_read_all_data from supabase_read_only_user;
            drop role authentication_audit_test_superuser;
            drop role supabase_audit_test_system_role;
            drop role supabase_read_only_user;
            """
        )


def test_verification_rejects_ordinary_effective_and_direct_access() -> None:
    apply_migration()
    execute(
        """
        drop role if exists authentication_audit_test_ordinary_rogue;
        create role authentication_audit_test_ordinary_rogue nologin;
        grant pg_read_all_data to authentication_audit_test_ordinary_rogue;
        """
    )
    try:
        assert execute(
            """
            select
                has_table_privilege(
                    'authentication_audit_test_ordinary_rogue',
                    'public.authentication_audit_events',
                    'SELECT'
                ),
                not exists (
                    select 1
                    from pg_catalog.pg_class as table_definition
                    cross join lateral pg_catalog.aclexplode(
                        coalesce(
                            table_definition.relacl,
                            pg_catalog.acldefault(
                                'r',
                                table_definition.relowner
                            )
                        )
                    ) as privilege
                    where table_definition.oid =
                          'public.authentication_audit_events'::regclass
                      and privilege.grantee =
                          to_regrole(
                              'authentication_audit_test_ordinary_rogue'
                          )
                )
            """,
            fetch=True,
        ) == [(True, True)]
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="unexpected role has effective",
        ):
            run_sql_file(VERIFICATION)

        execute(
            """
            revoke pg_read_all_data
                from authentication_audit_test_ordinary_rogue;
            grant select on public.authentication_audit_events
                to authentication_audit_test_ordinary_rogue;
            """
        )
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="table ACL contains an unexpected grant",
        ):
            run_sql_file(VERIFICATION)
    finally:
        execute(
            """
            revoke all privileges on public.authentication_audit_events
                from authentication_audit_test_ordinary_rogue;
            revoke pg_read_all_data
                from authentication_audit_test_ordinary_rogue;
            drop role authentication_audit_test_ordinary_rogue;
            """
        )


def test_verification_rejects_direct_acl_for_bypassrls_role() -> None:
    apply_migration()
    execute(
        """
        grant select on public.authentication_audit_events
            to rogue_auth_role
        """
    )

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="table ACL contains an unexpected grant",
    ):
        run_sql_file(VERIFICATION)


def test_migration_removes_rogue_table_column_and_function_grants() -> None:
    apply_migration()
    migration_owner = execute("select current_user", fetch=True)[0][0]
    execute(
        """
        grant usage on schema public to rogue_auth_role;
        grant insert, update, delete on
            public.authentication_audit_events to rogue_auth_role;
        grant select on public.authentication_audit_events
            to rogue_auth_role with grant option;
        grant select (id), insert (event_type), update (outcome)
            on public.authentication_audit_events to rogue_auth_role;
        grant select (id) on public.authentication_audit_events to anon;
        grant update (outcome)
            on public.authentication_audit_events to authenticated;
        grant insert (event_type)
            on public.authentication_audit_events to service_role;
        grant execute on function public.record_authentication_audit_event(
            uuid,text,text,text,uuid,text,text,text,text
        ) to rogue_auth_role with grant option;
        """
    )
    execute_as(
        "rogue_auth_role",
        """
        grant select on public.authentication_audit_events to anon;
        grant execute on function public.record_authentication_audit_event(
            uuid,text,text,text,uuid,text,text,text,text
        ) to anon;
        """,
    )

    apply_migration()
    run_sql_file(VERIFICATION)

    assert execute(
        """
        select
            attribute_definition.attname,
            role_definition.rolname,
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
        order by
            attribute_definition.attname,
            role_definition.rolname,
            privilege.privilege_type
        """,
        fetch=True,
    ) == [("user_id", migration_owner, "UPDATE", False)]
    assert execute(
        """
        select
            has_schema_privilege('anon','public','USAGE'),
            has_schema_privilege('authenticated','public','USAGE'),
            has_schema_privilege('service_role','public','USAGE'),
            has_schema_privilege('anon','public','CREATE'),
            has_schema_privilege('authenticated','public','CREATE'),
            has_schema_privilege('service_role','public','CREATE')
        """,
        fetch=True,
    ) == [(True, True, True, False, False, False)]
    assert execute(
        """
        select
            has_table_privilege(
                'rogue_auth_role',
                'public.authentication_audit_events',
                'INSERT'
            ),
            has_any_column_privilege(
                'rogue_auth_role',
                'public.authentication_audit_events',
                'SELECT'
            ),
            has_function_privilege(
                'rogue_auth_role',
                'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)',
                'EXECUTE'
            )
        """,
        fetch=True,
    ) == [(False, False, False)]


@pytest.mark.parametrize(
    "hostile_schema_grant",
    [
        "grant create on schema public to public",
        "grant create on schema public to anon",
        "grant create on schema public to authenticated",
        "grant create on schema public to service_role",
        "grant usage on schema public to anon with grant option",
    ],
)
def test_preflight_and_verification_reject_unsafe_schema_grants(
    hostile_schema_grant: str,
) -> None:
    apply_migration()
    execute(hostile_schema_grant)

    with pytest.raises(
        psycopg.errors.InsufficientPrivilege,
        match="schema",
    ):
        run_sql_file(PREFLIGHT)
    with pytest.raises(
        psycopg.errors.RaiseException,
        match="schema",
    ):
        run_sql_file(VERIFICATION)


def test_schema_rls_grants_indexes_fk_and_no_json_or_correlation_uniqueness() -> None:
    apply_migration()
    migration_owner = execute("select current_user", fetch=True)[0][0]

    columns = execute(
        """
        select column_name, data_type, is_nullable, column_default
        from information_schema.columns
        where table_schema='public'
          and table_name='authentication_audit_events'
        order by ordinal_position
        """,
        fetch=True,
    )
    assert [column[0] for column in columns] == [
        "id",
        "occurred_at",
        "event_type",
        "outcome",
        "auth_method",
        "user_id",
        "failure_category",
        "revocation_reason",
        "correlation_id",
        "source_environment",
    ]
    assert all(column[1] != "jsonb" for column in columns)
    assert columns[0][3] is None
    assert "now()" in columns[1][3]

    assert execute(
        """
        select relrowsecurity
        from pg_catalog.pg_class
        where oid='public.authentication_audit_events'::regclass
        """,
        fetch=True,
    ) == [(True,)]
    assert execute(
        """
        select
            role_definition.rolname,
            privilege.privilege_type,
            privilege.is_grantable
        from pg_catalog.pg_class as table_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                table_definition.relacl,
                pg_catalog.acldefault('r', table_definition.relowner)
            )
        ) as privilege
        join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where table_definition.oid =
              'public.authentication_audit_events'::regclass
        order by role_definition.rolname, privilege.privilege_type
        """,
        fetch=True,
    ) == sorted(
        [
            (migration_owner, "INSERT", False),
            (migration_owner, "SELECT", False),
            ("service_role", "SELECT", False),
        ]
    )
    assert execute(
        """
        select count(*)
        from pg_catalog.pg_policies
        where schemaname='public'
          and tablename='authentication_audit_events'
        """,
        fetch=True,
    ) == [(0,)]
    assert execute(
        """
        select
            has_schema_privilege('anon','public','USAGE'),
            has_schema_privilege('authenticated','public','USAGE'),
            has_schema_privilege('service_role','public','USAGE'),
            has_schema_privilege('anon','public','CREATE'),
            has_schema_privilege('authenticated','public','CREATE'),
            has_schema_privilege('service_role','public','CREATE')
        """,
        fetch=True,
    ) == [(True, True, True, False, False, False)]
    assert execute(
        """
        select
            attribute_definition.attname,
            role_definition.rolname,
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
        order by
            attribute_definition.attname,
            role_definition.rolname,
            privilege.privilege_type
        """,
        fetch=True,
    ) == [("user_id", migration_owner, "UPDATE", False)]
    assert execute(
        """
        select
            has_table_privilege('service_role','public.authentication_audit_events','SELECT'),
            has_table_privilege('service_role','public.authentication_audit_events','INSERT'),
            has_table_privilege('service_role','public.authentication_audit_events','UPDATE'),
            has_table_privilege('service_role','public.authentication_audit_events','DELETE'),
            has_column_privilege(
                'service_role',
                'public.authentication_audit_events',
                'user_id',
                'UPDATE'
            ),
            has_table_privilege('anon','public.authentication_audit_events','SELECT'),
            has_column_privilege(
                'anon',
                'public.authentication_audit_events',
                'user_id',
                'UPDATE'
            ),
            has_table_privilege('authenticated','public.authentication_audit_events','INSERT'),
            has_column_privilege(
                'authenticated',
                'public.authentication_audit_events',
                'user_id',
                'UPDATE'
            )
        """,
        fetch=True,
    ) == [(True, False, False, False, False, False, False, False, False)]

    function_security = execute(
        """
        select
            p.prosecdef,
            p.proconfig,
            owner.rolname,
            has_function_privilege(
                'service_role',
                p.oid,
                'EXECUTE'
            ),
            has_function_privilege('anon',p.oid,'EXECUTE'),
            has_function_privilege('authenticated',p.oid,'EXECUTE')
        from pg_catalog.pg_proc p
        join pg_catalog.pg_roles owner on owner.oid=p.proowner
        where p.oid = 'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'::regprocedure
        """,
        fetch=True,
    )
    assert function_security == [
        (
            True,
            ["search_path=pg_catalog"],
            migration_owner,
            True,
            False,
            False,
        )
    ]
    assert execute(
        """
        select
            role_definition.rolname,
            privilege.privilege_type,
            privilege.is_grantable
        from pg_catalog.pg_proc as function_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                function_definition.proacl,
                pg_catalog.acldefault('f', function_definition.proowner)
            )
        ) as privilege
        join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where function_definition.oid =
              'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'::regprocedure
        order by role_definition.rolname
        """,
        fetch=True,
    ) == sorted(
        [
            (migration_owner, "EXECUTE", False),
            ("service_role", "EXECUTE", False),
        ]
    )

    indexes = execute(
        """
        select
            index_definition.relname,
            index_catalog.indisunique,
            index_catalog.indisprimary,
            index_catalog.indisvalid,
            index_catalog.indisready,
            index_catalog.indislive,
            array(
                select coalesce(
                    (
                        select attribute_definition.attname
                        from pg_catalog.pg_attribute as attribute_definition
                        where attribute_definition.attrelid =
                              index_catalog.indrelid
                          and attribute_definition.attnum =
                              index_catalog.indkey[key_position - 1]
                    ),
                    pg_catalog.pg_get_indexdef(
                        index_catalog.indexrelid,
                        key_position,
                        true
                    )
                )
                from pg_catalog.generate_series(
                    1,
                    index_catalog.indnkeyatts
                ) as key_position
                order by key_position
            ),
            array(
                select
                    case
                        when (
                            index_catalog.indoption[key_position - 1] & 1
                        ) = 1 then 'desc'
                        else 'asc'
                    end
                    || ':'
                    || case
                        when (
                            index_catalog.indoption[key_position - 1] & 2
                        ) = 2 then 'nulls_first'
                        else 'nulls_last'
                    end
                from pg_catalog.generate_series(
                    1,
                    index_catalog.indnkeyatts
                ) as key_position
                order by key_position
            ),
            coalesce(
                pg_catalog.pg_get_expr(
                    index_catalog.indpred,
                    index_catalog.indrelid,
                    true
                ),
                ''
            )
        from pg_catalog.pg_index as index_catalog
        join pg_catalog.pg_class as index_definition
          on index_definition.oid=index_catalog.indexrelid
        where index_catalog.indrelid =
              'public.authentication_audit_events'::regclass
        order by index_definition.relname
        """,
        fetch=True,
    )
    assert indexes == [
        (
            "authentication_audit_events_pkey",
            True,
            True,
            True,
            True,
            True,
            ["id"],
            ["asc:nulls_last"],
            "",
        ),
        (
            "idx_authentication_audit_events_occurred_at",
            False,
            False,
            True,
            True,
            True,
            ["occurred_at"],
            ["desc:nulls_first"],
            "",
        ),
        (
            "idx_authentication_audit_events_type_outcome_occurred_at",
            False,
            False,
            True,
            True,
            True,
            ["event_type", "outcome", "occurred_at"],
            ["asc:nulls_last", "asc:nulls_last", "desc:nulls_first"],
            "",
        ),
        (
            "idx_authentication_audit_events_user_occurred_at",
            False,
            False,
            True,
            True,
            True,
            ["user_id", "occurred_at"],
            ["asc:nulls_last", "desc:nulls_first"],
            "user_id IS NOT NULL",
        ),
    ]
    assert execute(
        """
        select confdeltype
        from pg_catalog.pg_constraint
        where conrelid='public.authentication_audit_events'::regclass
          and contype='f'
        """,
        fetch=True,
    ) == [("n",)]


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_type": "unknown"},
        {"outcome": "unknown"},
        {"auth_method": "unknown"},
        {"outcome": "failed", "failure_category": None},
        {"outcome": "succeeded", "failure_category": "internal_error"},
        {"event_type": "login", "revocation_reason": "logout"},
        {"event_type": "token_revocation", "revocation_reason": None},
        {"event_type": "logout", "auth_method": "password"},
        {
            "event_type": "login",
            "auth_method": "google",
            "outcome": "failed",
            "failure_category": "invalid_credentials",
        },
        {
            "event_type": "logout",
            "auth_method": "bearer",
            "outcome": "failed",
            "failure_category": "invalid_credentials",
        },
        {
            "event_type": "token_revocation",
            "auth_method": "google",
            "revocation_reason": "logout",
        },
        {
            "event_type": "token_revocation",
            "auth_method": "bearer",
            "revocation_reason": "password_reset",
        },
        {
            "event_type": "token_revocation",
            "auth_method": "google",
            "revocation_reason": "google_unlinked",
        },
        {
            "event_type": "token_revocation",
            "auth_method": "password",
            "revocation_reason": "password_set",
        },
        {
            "event_type": "token_revocation",
            "auth_method": "password",
            "revocation_reason": "password_removed",
        },
        {
            "event_type": "token_revocation",
            "auth_method": "recovery",
            "revocation_reason": "account_deleted",
        },
        {"correlation_id": "short"},
        {"correlation_id": "contains spaces"},
        {"source_environment": ""},
        {"source_environment": "unsafe/environment"},
    ],
)
def test_rpc_rejects_invalid_or_cross_column_values(overrides: dict) -> None:
    apply_migration()
    params = {
        "event_type": "login",
        "outcome": "succeeded",
        "auth_method": "password",
        "failure_category": None,
        "revocation_reason": None,
    }
    params.update(overrides)

    with pytest.raises(psycopg.errors.CheckViolation):
        execute_as("service_role", RPC_SQL, rpc_params(**params))


def test_phase_2_revocation_reason_and_method_matrix() -> None:
    apply_migration()
    approved = [
        ("logout", "bearer"),
        ("google_unlinked", "password"),
        ("password_set", "google"),
        ("password_removed", "google"),
        ("password_reset", "recovery"),
        ("account_deleted", "password"),
        ("account_deleted", "google"),
    ]

    for index, (reason, method) in enumerate(approved):
        assert execute_as(
            "service_role",
            RPC_SQL,
            rpc_params(
                event_id=f"00000000-0000-4000-8000-{index + 1:012d}",
                event_type="token_revocation",
                outcome="succeeded",
                auth_method=method,
                revocation_reason=reason,
                correlation_id=f"phase2-{index:02d}",
            ),
            fetch=True,
        ) == [(True,)]

    assert execute(
        """
        select revocation_reason, auth_method, outcome
        from public.authentication_audit_events
        order by revocation_reason, auth_method
        """,
        fetch=True,
    ) == sorted(
        [(reason, method, "succeeded") for reason, method in approved]
    )


def test_event_id_is_idempotency_key_and_correlation_is_grouping_only() -> None:
    apply_migration()
    user_id = add_user()
    event_id = str(uuid4())
    params = rpc_params(event_id=event_id, user_id=user_id)

    assert execute_as("service_role", RPC_SQL, params, fetch=True) == [(True,)]
    assert execute_as("service_role", RPC_SQL, params, fetch=True) == [(False,)]
    conflicting_params = list(params)
    conflicting_params[2] = "failed"
    conflicting_params[5] = "internal_error"
    with pytest.raises(
        psycopg.errors.UniqueViolation,
        match="conflicts with existing immutable payload",
    ):
        execute_as("service_role", RPC_SQL, tuple(conflicting_params), fetch=True)
    assert execute_as(
        "service_role",
        RPC_SQL,
        rpc_params(user_id=user_id, correlation_id=params[7]),
        fetch=True,
    ) == [(True,)]
    assert execute(
        """
        select count(*)
        from public.authentication_audit_events
        where correlation_id=%s
        """,
        (params[7],),
        fetch=True,
    ) == [(2,)]


def test_concurrent_exact_retries_insert_once() -> None:
    apply_migration()
    user_id = add_user()
    params = rpc_params(event_id=str(uuid4()), user_id=user_id)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _index: execute_as(
                    "service_role",
                    RPC_SQL,
                    params,
                    fetch=True,
                )[0][0],
                range(16),
            )
        )

    assert results.count(True) == 1
    assert results.count(False) == 15
    assert execute(
        "select count(*) from public.authentication_audit_events where id=%s",
        (params[0],),
        fetch=True,
    ) == [(1,)]


def test_concurrent_conflicting_retries_are_deterministic() -> None:
    apply_migration()
    event_id = str(uuid4())
    first = rpc_params(event_id=event_id, correlation_id="concurrent-conflict")
    second = rpc_params(
        event_id=event_id,
        outcome="failed",
        failure_category="internal_error",
        correlation_id="concurrent-conflict",
    )

    def write(params: tuple) -> str:
        try:
            result = execute_as(
                "service_role",
                RPC_SQL,
                params,
                fetch=True,
            )
            return f"result:{result[0][0]}"
        except psycopg.errors.UniqueViolation:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(write, (first, second)))

    assert sorted(results) == ["conflict", "result:True"]
    assert execute(
        "select count(*) from public.authentication_audit_events where id=%s",
        (event_id,),
        fetch=True,
    ) == [(1,)]


def test_fk_set_null_and_time_window_querying() -> None:
    apply_migration()
    user_id = add_user()
    event_ids = [str(uuid4()) for _ in range(3)]
    original_params: list[tuple] = []
    for event_id in event_ids:
        params = rpc_params(event_id=event_id, user_id=user_id)
        original_params.append(params)
        execute_as(
            "service_role",
            RPC_SQL,
            params,
        )

    execute(
        """
        update public.authentication_audit_events
        set occurred_at = case id
            when %s then '2026-01-01T00:00:00Z'::timestamptz
            when %s then '2026-01-02T00:00:00Z'::timestamptz
            else '2026-01-03T00:00:00Z'::timestamptz
        end
        """,
        tuple(event_ids[:2]),
    )
    window_rows = execute(
        """
        select id
        from public.authentication_audit_events
        where occurred_at >= %s
          and occurred_at < %s
        order by occurred_at
        """,
        (
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            datetime(2026, 1, 3, tzinfo=timezone.utc),
        ),
        fetch=True,
    )
    assert window_rows == [(UUID(event_ids[1]),)]

    execute("delete from public.users where id=%s", (user_id,))
    assert execute(
        """
        select count(*)
        from public.authentication_audit_events
        where user_id is null
        """,
        fetch=True,
    ) == [(3,)]

    # ON DELETE SET NULL changes immutable payload comparison. Replaying the
    # old user UUID is therefore a stable sanitized conflict, not an exact
    # replay, and no extra deleted-user identifier is retained.
    with pytest.raises(
        psycopg.errors.UniqueViolation,
        match="conflicts with existing immutable payload",
    ) as conflict:
        execute_as(
            "service_role",
            RPC_SQL,
            original_params[0],
            fetch=True,
        )
    assert user_id not in str(conflict.value)


def test_exact_table_and_rpc_permissions_are_exercised() -> None:
    execute("grant usage on schema public to rogue_auth_role")
    apply_migration()
    event_id = str(uuid4())
    assert execute_as(
        "service_role",
        RPC_SQL,
        rpc_params(event_id=event_id),
        fetch=True,
    ) == [(True,)]

    for role in ("anon", "authenticated", "rogue_auth_role"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as(
                role,
                "select * from public.authentication_audit_events",
                fetch=True,
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as(
                role,
                "select id from public.authentication_audit_events",
                fetch=True,
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as(
                role,
                """
                insert into public.authentication_audit_events (
                    id,event_type,outcome,auth_method,correlation_id,source_environment
                )
                values (
                    gen_random_uuid(),'login','succeeded','password','direct-write','test'
                )
                """,
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as(
                role,
                """
                update public.authentication_audit_events
                set source_environment='changed'
                """,
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as(
                role,
                """
                update public.authentication_audit_events
                set outcome='failed'
                """,
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as(
                role,
                """
                update public.authentication_audit_events
                set user_id = null
                """,
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as(
                role,
                "delete from public.authentication_audit_events",
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as(role, RPC_SQL, rpc_params(), fetch=True)

    assert execute_as(
        "service_role",
        "select id from public.authentication_audit_events where id=%s",
        (event_id,),
        fetch=True,
    ) == [(UUID(event_id),)]

    for statement in (
        """
        insert into public.authentication_audit_events (
            id,event_type,outcome,auth_method,correlation_id,source_environment
        )
        values (
            gen_random_uuid(),'login','succeeded','password','direct-write','test'
        )
        """,
        """
        update public.authentication_audit_events
        set source_environment='changed'
        """,
        """
        insert into public.authentication_audit_events (event_type)
        values ('login')
        """,
        """
        update public.authentication_audit_events
        set outcome='failed'
        """,
        """
        update public.authentication_audit_events
        set user_id = null
        """,
        "delete from public.authentication_audit_events",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as("service_role", statement)


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_no_policy_rls_denies_clients_even_with_temporary_table_grants(
    role: str,
) -> None:
    apply_migration()
    event_id = str(uuid4())
    assert execute_as(
        "service_role",
        RPC_SQL,
        rpc_params(event_id=event_id),
        fetch=True,
    ) == [(True,)]

    def exercise(statement: str, *, fetch: bool = False):
        with psycopg.connect(DATABASE_URL, autocommit=False) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "grant select, insert, update, delete on "
                        "public.authentication_audit_events to "
                        + role
                    )
                    cursor.execute("set local role " + role)
                    cursor.execute(statement)
                    return cursor.fetchall() if fetch else None
            finally:
                connection.rollback()

    assert exercise(
        "select id from public.authentication_audit_events",
        fetch=True,
    ) == []
    assert exercise(
        """
        update public.authentication_audit_events
        set source_environment='changed'
        returning id
        """,
        fetch=True,
    ) == []
    assert exercise(
        "delete from public.authentication_audit_events returning id",
        fetch=True,
    ) == []
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        exercise(
            """
            insert into public.authentication_audit_events (
                id,event_type,outcome,auth_method,correlation_id,source_environment
            )
            values (
                gen_random_uuid(),'login','succeeded','password','rls-denied','test'
            )
            """
        )
