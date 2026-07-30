"""Real PostgreSQL checks for ISSUE-1031 security attribution foundations.

Set SECURITY_ATTRIBUTION_DATABASE_URL to a disposable PostgreSQL 16 database.
These tests destroy and recreate the public schema and must never target a
shared database.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest


DATABASE_URL = os.getenv("SECURITY_ATTRIBUTION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="SECURITY_ATTRIBUTION_DATABASE_URL is not configured",
)

BACKEND_DIR = Path(__file__).parents[1]
MIGRATION = BACKEND_DIR / "migrations" / "security_request_attribution.sql"
PREFLIGHT = (
    BACKEND_DIR
    / "scripts"
    / "security_request_attribution_migration_preflight.sql"
)
VERIFICATION = (
    BACKEND_DIR
    / "scripts"
    / "verify_security_request_attribution_migration.sql"
)
SCHEMA = BACKEND_DIR / "schema.sql"

ZERO_UUID = UUID("00000000-0000-0000-0000-000000000000")
PSEUDONYM = "A" * 43


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
            create role security_attribution_rogue nologin;
        exception when duplicate_object then null;
        end
        $$;
        do $$
        begin
            create role security_attribution_migrator nologin noinherit;
        exception when duplicate_object then null;
        end
        $$;
        alter role service_role bypassrls;
        alter role security_attribution_migrator noinherit;
        grant usage on schema public to
            service_role,
            anon,
            authenticated;
        grant usage, create on schema public
            to security_attribution_migrator;
        do $$
        begin
            if pg_catalog.current_setting(
                'server_version_num'
            )::integer >= 160000 then
                execute
                    'grant service_role, anon, authenticated '
                    'to security_attribution_migrator with set true';
            else
                execute
                    'grant service_role, anon, authenticated '
                    'to security_attribution_migrator';
            end if;
        end
        $$;
        """
    )


def apply_migration() -> None:
    run_sql_file(MIGRATION)


def valid_ingestion_params(
    *,
    request_event_id: UUID | None = None,
    occurred_at: datetime | None = None,
    pseudonym: str = PSEUDONYM,
    epoch: str | None = None,
    environment: str = "development",
    event_category: str = "session_security_change",
    route_key: str = "auth_logout",
    method: str = "POST",
    outcome: str = "succeeded",
    failure_category: str | None = None,
) -> tuple:
    occurred = occurred_at or (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    return (
        request_event_id or uuid4(),
        occurred,
        pseudonym,
        epoch or occurred.strftime("%Y-%m"),
        1,
        environment,
        event_category,
        route_key,
        method,
        outcome,
        failure_category,
        uuid4(),
    )


INGEST_SQL = """
    select public.record_security_request_attribution_event(
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
"""


def ingest_as(role: str, params: tuple) -> str:
    return execute_as(role, INGEST_SQL, params, fetch=True)[0][0]


def insert_attribution(
    *,
    row_id: UUID,
    request_event_id: UUID,
    occurred_at: datetime,
    pseudonym: str = PSEUDONYM,
) -> None:
    execute(
        """
        insert into public.security_request_attribution_events (
            id,
            request_event_id,
            occurred_at,
            account_pseudonym,
            pseudonym_epoch,
            pseudonym_key_version,
            environment,
            event_category,
            route_key,
            http_method,
            outcome,
            failure_category
        )
        values (
            %s, %s, %s, %s, %s, 1, 'development',
            'session_security_change', 'auth_logout', 'POST',
            'succeeded', null
        )
        """,
        (
            row_id,
            request_event_id,
            occurred_at,
            pseudonym,
            occurred_at.strftime("%Y-%m"),
        ),
    )


def insert_access(
    *,
    row_id: UUID,
    access_event_id: UUID,
    occurred_at: datetime,
) -> None:
    execute(
        """
        insert into public.security_investigation_access_events (
            id,
            access_event_id,
            occurred_at,
            incident_id,
            investigator_capability,
            action_category,
            query_window_start,
            query_window_end,
            requested_limit,
            result_count,
            environment,
            outcome,
            failure_category
        )
        values (
            %s, %s, %s, %s, 'owner_activation_gate', 'query',
            %s, %s, 10, 0, 'development', 'succeeded', null
        )
        """,
        (
            row_id,
            access_event_id,
            occurred_at,
            uuid4(),
            occurred_at,
            occurred_at + timedelta(seconds=1),
        ),
    )


def query_events(
    *,
    incident_id: UUID,
    window_start: datetime,
    window_end: datetime,
    result_limit: int,
) -> list[tuple]:
    return execute(
        """
        select *
        from public.query_security_request_attribution_events(
            %s, 'development', %s, %s, %s
        )
        """,
        (incident_id, window_start, window_end, result_limit),
        fetch=True,
    )


def object_snapshot() -> dict[str, list[tuple]]:
    return {
        "columns": execute(
            """
            select
                table_definition.relname,
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
            from pg_catalog.pg_class as table_definition
            join pg_catalog.pg_attribute as attribute_definition
              on attribute_definition.attrelid = table_definition.oid
            left join pg_catalog.pg_attrdef as default_definition
              on default_definition.adrelid = table_definition.oid
             and default_definition.adnum = attribute_definition.attnum
            where table_definition.oid in (
                'public.security_request_attribution_events'::regclass,
                'public.security_investigation_access_events'::regclass
            )
              and attribute_definition.attnum > 0
              and not attribute_definition.attisdropped
            order by table_definition.relname, attribute_definition.attnum
            """,
            fetch=True,
        ),
        "constraints": execute(
            """
            select
                table_definition.relname,
                constraint_definition.conname,
                constraint_definition.contype,
                pg_catalog.pg_get_constraintdef(
                    constraint_definition.oid,
                    true
                )
            from pg_catalog.pg_constraint as constraint_definition
            join pg_catalog.pg_class as table_definition
              on table_definition.oid = constraint_definition.conrelid
            where table_definition.oid in (
                'public.security_request_attribution_events'::regclass,
                'public.security_investigation_access_events'::regclass
            )
            order by table_definition.relname,
                     constraint_definition.conname
            """,
            fetch=True,
        ),
        "indexes": execute(
            """
            select
                table_definition.relname,
                index_relation.relname,
                pg_catalog.pg_get_indexdef(index_definition.indexrelid),
                index_definition.indisunique,
                index_definition.indisvalid,
                index_definition.indisready
            from pg_catalog.pg_index as index_definition
            join pg_catalog.pg_class as table_definition
              on table_definition.oid = index_definition.indrelid
            join pg_catalog.pg_class as index_relation
              on index_relation.oid = index_definition.indexrelid
            where table_definition.oid in (
                'public.security_request_attribution_events'::regclass,
                'public.security_investigation_access_events'::regclass
            )
            order by table_definition.relname, index_relation.relname
            """,
            fetch=True,
        ),
        "table_security": execute(
            """
            select
                table_definition.relname,
                pg_catalog.pg_get_userbyid(table_definition.relowner),
                table_definition.relrowsecurity,
                table_definition.relforcerowsecurity,
                table_definition.relacl::text
            from pg_catalog.pg_class as table_definition
            where table_definition.oid in (
                'public.security_request_attribution_events'::regclass,
                'public.security_investigation_access_events'::regclass
            )
            order by table_definition.relname
            """,
            fetch=True,
        ),
        "column_acl": execute(
            """
            select
                table_definition.relname,
                attribute_definition.attname,
                attribute_definition.attacl::text
            from pg_catalog.pg_attribute as attribute_definition
            join pg_catalog.pg_class as table_definition
              on table_definition.oid = attribute_definition.attrelid
            where table_definition.oid in (
                'public.security_request_attribution_events'::regclass,
                'public.security_investigation_access_events'::regclass
            )
              and attribute_definition.attnum > 0
              and not attribute_definition.attisdropped
              and attribute_definition.attacl is not null
            order by table_definition.relname, attribute_definition.attname
            """,
            fetch=True,
        ),
        "functions": execute(
            """
            select
                function_definition.proname,
                pg_catalog.pg_get_userbyid(function_definition.proowner),
                pg_catalog.pg_get_function_identity_arguments(
                    function_definition.oid
                ),
                pg_catalog.pg_get_function_result(function_definition.oid),
                function_definition.prosecdef,
                function_definition.provolatile,
                function_definition.proparallel,
                function_definition.proconfig,
                function_definition.proacl::text,
                function_definition.prosrc
            from pg_catalog.pg_proc as function_definition
            where function_definition.pronamespace =
                  'public'::regnamespace
              and function_definition.proname in (
                  'record_security_request_attribution_event',
                  'query_security_request_attribution_events',
                  'cleanup_security_request_attribution_events',
                  'cleanup_security_investigation_access_events'
              )
            order by function_definition.proname
            """,
            fetch=True,
        ),
    }


def test_preflight_reapplication_and_rollback_only_verification() -> None:
    run_sql_file(PREFLIGHT)
    apply_migration()
    run_sql_file(PREFLIGHT)
    before = object_snapshot()

    apply_migration()
    assert object_snapshot() == before

    run_sql_file(VERIFICATION)
    assert execute(
        """
        select
            (
                select count(*)
                from public.security_request_attribution_events
            ),
            (
                select count(*)
                from public.security_investigation_access_events
            )
        """,
        fetch=True,
    ) == [(0, 0)]


def test_exact_columns_keys_constraints_and_no_privacy_forbidden_fields() -> None:
    apply_migration()

    expected_attribution_columns = [
        ("id", "uuid", True, "gen_random_uuid()"),
        ("request_event_id", "uuid", True, None),
        ("occurred_at", "timestamp with time zone", True, None),
        ("account_pseudonym", "text", True, None),
        ("pseudonym_epoch", "text", True, None),
        ("pseudonym_key_version", "smallint", True, None),
        ("environment", "text", True, None),
        ("event_category", "text", True, None),
        ("route_key", "text", True, None),
        ("http_method", "text", True, None),
        ("outcome", "text", True, None),
        ("failure_category", "text", False, None),
        ("server_correlation_id", "uuid", False, None),
        ("created_at", "timestamp with time zone", True, "now()"),
    ]
    expected_access_columns = [
        ("id", "uuid", True, "gen_random_uuid()"),
        ("access_event_id", "uuid", True, None),
        ("occurred_at", "timestamp with time zone", True, None),
        ("incident_id", "uuid", True, None),
        ("investigator_capability", "text", True, None),
        ("action_category", "text", True, None),
        ("query_window_start", "timestamp with time zone", True, None),
        ("query_window_end", "timestamp with time zone", True, None),
        ("requested_limit", "integer", True, None),
        ("result_count", "integer", False, None),
        ("environment", "text", True, None),
        ("outcome", "text", True, None),
        ("failure_category", "text", False, None),
        ("created_at", "timestamp with time zone", True, "now()"),
    ]

    rows = object_snapshot()["columns"]
    assert [row[1:] for row in rows if row[0].startswith("security_invest")] == (
        expected_access_columns
    )
    assert [row[1:] for row in rows if row[0].startswith("security_request")] == (
        expected_attribution_columns
    )

    forbidden_fragments = {
        "account_id",
        "target",
        "email",
        "username",
        "phone",
        "display_name",
        "ip",
        "user_agent",
        "body",
        "header",
        "cookie",
        "authorization",
        "jwt",
        "token",
        "credential",
        "url",
        "query_string",
        "metadata",
    }
    all_columns = {row[1] for row in rows}
    assert not {
        column
        for column in all_columns
        if any(fragment in column for fragment in forbidden_fragments)
    }

    constraint_rows = object_snapshot()["constraints"]
    assert sum(row[2] == "p" for row in constraint_rows) == 2
    assert sum(row[2] == "u" for row in constraint_rows) == 2
    assert sum(row[2] == "c" for row in constraint_rows) == 23


@pytest.mark.parametrize(
    ("param_index", "invalid_value"),
    [
        (0, ZERO_UUID),
        (2, "A" * 42),
        (2, "A" * 42 + "="),
        (2, "A" * 42 + "+"),
        (3, "2026-7"),
        (5, "test"),
        (6, "arbitrary_event"),
        (7, "arbitrary_route"),
        (8, "OPTIONS"),
        (9, "unknown"),
        (10, "arbitrary_failure"),
    ],
    ids=[
        "zero-event-id",
        "short-pseudonym",
        "padded-pseudonym",
        "non-base64url-pseudonym",
        "malformed-epoch",
        "environment",
        "event-category",
        "route-key",
        "method",
        "outcome",
        "failure-category",
    ],
)
def test_ingestion_rejects_malformed_or_unbounded_values(
    param_index: int,
    invalid_value: object,
) -> None:
    apply_migration()
    params = list(valid_ingestion_params())
    params[param_index] = invalid_value

    with pytest.raises(psycopg.errors.InvalidParameterValue):
        ingest_as("service_role", tuple(params))

    assert execute(
        "select count(*) from public.security_request_attribution_events",
        fetch=True,
    ) == [(0,)]


@pytest.mark.parametrize(
    (
        "capability",
        "action",
        "window_days",
        "requested_limit",
        "result_count",
        "environment",
    ),
    [
        ("arbitrary", "query", 1, 10, 0, "development"),
        ("owner_activation_gate", "export", 1, 10, 0, "development"),
        ("owner_activation_gate", "query", 32, 10, 0, "development"),
        ("owner_activation_gate", "query", 1, 0, 0, "development"),
        ("owner_activation_gate", "query", 1, 10, 11, "development"),
        ("owner_activation_gate", "query", 1, 10, 0, "test"),
    ],
    ids=[
        "capability",
        "action",
        "window",
        "requested-limit",
        "result-count",
        "environment",
    ],
)
def test_investigation_access_constraints_reject_invalid_values(
    capability: str,
    action: str,
    window_days: int,
    requested_limit: int,
    result_count: int,
    environment: str,
) -> None:
    apply_migration()
    window_start = datetime.now(timezone.utc) - timedelta(days=40)

    with pytest.raises(psycopg.errors.CheckViolation):
        execute(
            """
            insert into public.security_investigation_access_events (
                access_event_id,
                occurred_at,
                incident_id,
                investigator_capability,
                action_category,
                query_window_start,
                query_window_end,
                requested_limit,
                result_count,
                environment,
                outcome,
                failure_category
            )
            values (
                %s, pg_catalog.now(), %s, %s, %s, %s, %s, %s, %s,
                %s, 'succeeded', null
            )
            """,
            (
                uuid4(),
                uuid4(),
                capability,
                action,
                window_start,
                window_start + timedelta(days=window_days),
                requested_limit,
                result_count,
                environment,
            ),
        )


def test_ingestion_is_idempotent_and_conflicting_replay_fails_safely() -> None:
    apply_migration()
    event_id = uuid4()
    params = valid_ingestion_params(request_event_id=event_id)

    assert ingest_as("service_role", params) == "inserted"
    assert ingest_as("service_role", params) == "already_recorded"
    assert execute(
        """
        select count(*)
        from public.security_request_attribution_events
        where request_event_id = %s
        """,
        (event_id,),
        fetch=True,
    ) == [(1,)]

    conflicting = list(params)
    conflicting[2] = "B" * 43
    with pytest.raises(
        psycopg.errors.UniqueViolation,
        match="immutable payload",
    ):
        ingest_as("service_role", tuple(conflicting))

    assert execute(
        """
        select account_pseudonym
        from public.security_request_attribution_events
        where request_event_id = %s
        """,
        (event_id,),
        fetch=True,
    ) == [(PSEUDONYM,)]


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_client_roles_cannot_execute_ingestion_or_query(role: str) -> None:
    apply_migration()

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        ingest_as(role, valid_ingestion_params())

    now = datetime.now(timezone.utc)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        execute_as(
            role,
            """
            select *
            from public.query_security_request_attribution_events(
                %s, 'development', %s, %s, 10
            )
            """,
            (uuid4(), now - timedelta(hours=1), now),
        )

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        execute_as(
            role,
            """
            select public.cleanup_security_request_attribution_events(
                pg_catalog.now() - interval '180 days',
                1
            )
            """,
        )


def test_service_role_has_execute_only_and_tables_are_append_only() -> None:
    apply_migration()
    params = valid_ingestion_params()
    assert ingest_as("service_role", params) == "inserted"

    for statement in (
        "select * from public.security_request_attribution_events",
        (
            "insert into public.security_request_attribution_events "
            "(request_event_id) values (gen_random_uuid())"
        ),
        "update public.security_request_attribution_events set id = id",
        "delete from public.security_request_attribution_events",
        "select * from public.security_investigation_access_events",
        "delete from public.security_investigation_access_events",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as("service_role", statement)

    now = datetime.now(timezone.utc)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        execute_as(
            "service_role",
            """
            select *
            from public.query_security_request_attribution_events(
                %s, 'development', %s, %s, 10
            )
            """,
            (uuid4(), now - timedelta(hours=1), now),
        )


def test_query_is_bounded_deterministic_pseudonymous_and_audited() -> None:
    apply_migration()
    occurred = datetime.now(timezone.utc) - timedelta(hours=1)
    row_ids = [
        UUID("00000000-0000-4000-8000-000000001401"),
        UUID("00000000-0000-4000-8000-000000001402"),
        UUID("00000000-0000-4000-8000-000000001403"),
    ]
    event_ids = [
        UUID("00000000-0000-4000-8000-000000001411"),
        UUID("00000000-0000-4000-8000-000000001412"),
        UUID("00000000-0000-4000-8000-000000001413"),
    ]
    insert_attribution(
        row_id=row_ids[2],
        request_event_id=event_ids[2],
        occurred_at=occurred + timedelta(seconds=1),
    )
    insert_attribution(
        row_id=row_ids[1],
        request_event_id=event_ids[1],
        occurred_at=occurred,
    )
    insert_attribution(
        row_id=row_ids[0],
        request_event_id=event_ids[0],
        occurred_at=occurred,
    )
    incident_id = uuid4()

    rows = query_events(
        incident_id=incident_id,
        window_start=occurred - timedelta(seconds=1),
        window_end=occurred + timedelta(seconds=2),
        result_limit=2,
    )

    assert [row[0] for row in rows] == ["succeeded", "succeeded"]
    assert [row[1] for row in rows] == event_ids[:2]
    assert all(row[3] == PSEUDONYM for row in rows)
    assert len(rows[0]) == 13
    assert execute(
        """
        select
            investigator_capability,
            action_category,
            requested_limit,
            result_count,
            environment,
            outcome,
            failure_category
        from public.security_investigation_access_events
        where incident_id = %s
        """,
        (incident_id,),
        fetch=True,
    ) == [
        (
            "owner_activation_gate",
            "query",
            2,
            2,
            "development",
            "succeeded",
            None,
        )
    ]


@pytest.mark.parametrize(
    ("window_delta", "result_limit", "failure_category"),
    [
        (timedelta(days=32), 10, "invalid_window"),
        (timedelta(days=1), 0, "limit_out_of_range"),
        (timedelta(days=1), 10001, "limit_out_of_range"),
    ],
)
def test_query_rejections_are_bounded_and_durably_audited(
    window_delta: timedelta,
    result_limit: int,
    failure_category: str,
) -> None:
    apply_migration()
    window_start = datetime.now(timezone.utc) - timedelta(days=40)
    incident_id = uuid4()

    rows = query_events(
        incident_id=incident_id,
        window_start=window_start,
        window_end=window_start + window_delta,
        result_limit=result_limit,
    )

    assert rows[0][0] == "rejected"
    assert all(value is None for value in rows[0][1:])
    assert execute(
        """
        select
            outcome,
            failure_category,
            requested_limit,
            query_window_end > query_window_start,
            query_window_end - query_window_start <= interval '31 days'
        from public.security_investigation_access_events
        where incident_id = %s
        """,
        (incident_id,),
        fetch=True,
    ) == [
        (
            "rejected",
            failure_category,
            1,
            True,
            True,
        )
    ]


def test_query_fails_closed_when_access_audit_cannot_persist() -> None:
    apply_migration()
    params = valid_ingestion_params()
    ingest_as("service_role", params)
    execute(
        """
        create function public.reject_investigation_access_insert()
        returns trigger
        language plpgsql
        as $$
        begin
            raise exception 'synthetic audit persistence failure';
        end;
        $$;
        create trigger reject_investigation_access_insert
        before insert on public.security_investigation_access_events
        for each statement
        execute function public.reject_investigation_access_insert();
        """
    )
    occurred = params[1]

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="investigation access audit persistence failed",
    ) as exc_info:
        query_events(
            incident_id=uuid4(),
            window_start=occurred - timedelta(seconds=1),
            window_end=occurred + timedelta(seconds=1),
            result_limit=10,
        )

    assert "synthetic" not in str(exc_info.value)
    assert execute(
        "select count(*) from public.security_investigation_access_events",
        fetch=True,
    ) == [(0,)]


def test_query_execution_failure_is_bounded_and_audited() -> None:
    apply_migration()
    execute(
        """
        alter table public.security_request_attribution_events
            rename to unavailable_security_request_attribution_events
        """
    )
    now = datetime.now(timezone.utc)
    incident_id = uuid4()

    rows = query_events(
        incident_id=incident_id,
        window_start=now - timedelta(hours=1),
        window_end=now,
        result_limit=10,
    )

    assert rows[0][0] == "failed"
    assert all(value is None for value in rows[0][1:])
    assert execute(
        """
        select outcome, failure_category, result_count
        from public.security_investigation_access_events
        where incident_id = %s
        """,
        (incident_id,),
        fetch=True,
    ) == [("failed", "query_failed", None)]


def test_retention_is_oldest_first_bounded_and_keeps_cutoff_rows() -> None:
    apply_migration()
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    attribution_ids = [
        UUID(f"00000000-0000-4000-8000-{value:012d}")
        for value in range(1421, 1426)
    ]
    access_ids = [
        UUID(f"00000000-0000-4000-8000-{value:012d}")
        for value in range(1431, 1436)
    ]
    times = [
        cutoff - timedelta(seconds=3),
        cutoff - timedelta(seconds=2),
        cutoff - timedelta(seconds=1),
        cutoff,
        cutoff + timedelta(seconds=1),
    ]
    for row_id, occurred_at in zip(attribution_ids, times, strict=True):
        insert_attribution(
            row_id=row_id,
            request_event_id=uuid4(),
            occurred_at=occurred_at,
        )
    for row_id, occurred_at in zip(access_ids, times, strict=True):
        insert_access(
            row_id=row_id,
            access_event_id=uuid4(),
            occurred_at=occurred_at,
        )

    for function_name in (
        "cleanup_security_request_attribution_events",
        "cleanup_security_investigation_access_events",
    ):
        assert execute_as(
            "service_role",
            f"select public.{function_name}(%s, 2)",
            (cutoff,),
            fetch=True,
        ) == [(2,)]
        assert execute_as(
            "service_role",
            f"select public.{function_name}(%s, 2)",
            (cutoff,),
            fetch=True,
        ) == [(1,)]
        assert execute_as(
            "service_role",
            f"select public.{function_name}(%s, 2)",
            (cutoff,),
            fetch=True,
        ) == [(0,)]

    assert execute(
        """
        select id
        from public.security_request_attribution_events
        order by occurred_at, id
        """,
        fetch=True,
    ) == [(attribution_ids[3],), (attribution_ids[4],)]
    assert execute(
        """
        select id
        from public.security_investigation_access_events
        order by occurred_at, id
        """,
        fetch=True,
    ) == [(access_ids[3],), (access_ids[4],)]


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
def test_cleanup_rejects_invalid_cutoffs_and_limits(
    cutoff_sql: str,
    limit_sql: str,
) -> None:
    apply_migration()

    for function_name in (
        "cleanup_security_request_attribution_events",
        "cleanup_security_investigation_access_events",
    ):
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            execute_as(
                "service_role",
                f"select public.{function_name}({cutoff_sql}, {limit_sql})",
            )


def test_failed_cleanup_batch_rolls_back_all_candidate_deletes() -> None:
    apply_migration()
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    row_ids = [uuid4(), uuid4()]
    for row_id in row_ids:
        insert_attribution(
            row_id=row_id,
            request_event_id=uuid4(),
            occurred_at=cutoff - timedelta(seconds=1),
        )
    execute(
        """
        create function public.reject_security_attribution_delete()
        returns trigger
        language plpgsql
        as $$
        begin
            raise exception 'synthetic cleanup failure';
        end;
        $$;
        create trigger reject_security_attribution_delete
        before delete on public.security_request_attribution_events
        for each statement
        execute function public.reject_security_attribution_delete();
        """
    )

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="synthetic cleanup failure",
    ):
        execute_as(
            "service_role",
            """
            select public.cleanup_security_request_attribution_events(
                %s,
                2
            )
            """,
            (cutoff,),
        )

    assert execute(
        """
        select id
        from public.security_request_attribution_events
        order by id
        """,
        fetch=True,
    ) == [(row_id,) for row_id in sorted(row_ids)]


def test_exact_owner_acl_rls_function_properties_and_activation_gate() -> None:
    apply_migration()
    owner = execute("select current_user", fetch=True)[0][0]

    assert execute(
        """
        select
            table_definition.relname,
            pg_catalog.pg_get_userbyid(table_definition.relowner),
            table_definition.relrowsecurity,
            table_definition.relforcerowsecurity,
            (
                select count(*)
                from pg_catalog.pg_policy as policy_definition
                where policy_definition.polrelid = table_definition.oid
            )
        from pg_catalog.pg_class as table_definition
        where table_definition.oid in (
            'public.security_request_attribution_events'::regclass,
            'public.security_investigation_access_events'::regclass
        )
        order by table_definition.relname
        """,
        fetch=True,
    ) == [
        (
            "security_investigation_access_events",
            owner,
            True,
            False,
            0,
        ),
        (
            "security_request_attribution_events",
            owner,
            True,
            False,
            0,
        ),
    ]

    assert execute(
        """
        select
            table_definition.relname,
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
        where table_definition.oid in (
            'public.security_request_attribution_events'::regclass,
            'public.security_investigation_access_events'::regclass
        )
        order by table_definition.relname, 2, 3
        """,
        fetch=True,
    ) == [
        (table_name, owner, privilege, False)
        for table_name in (
            "security_investigation_access_events",
            "security_request_attribution_events",
        )
        for privilege in ("DELETE", "INSERT", "SELECT")
    ]

    assert execute(
        """
        select
            table_definition.relname,
            attribute_definition.attname,
            coalesce(role_definition.rolname, 'PUBLIC'),
            privilege.privilege_type,
            privilege.is_grantable
        from pg_catalog.pg_attribute as attribute_definition
        join pg_catalog.pg_class as table_definition
          on table_definition.oid = attribute_definition.attrelid
        cross join lateral pg_catalog.aclexplode(
            attribute_definition.attacl
        ) as privilege
        left join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where table_definition.oid in (
            'public.security_request_attribution_events'::regclass,
            'public.security_investigation_access_events'::regclass
        )
          and attribute_definition.attnum > 0
          and not attribute_definition.attisdropped
        order by table_definition.relname
        """,
        fetch=True,
    ) == [
        (
            "security_investigation_access_events",
            "id",
            owner,
            "UPDATE",
            False,
        ),
        (
            "security_request_attribution_events",
            "id",
            owner,
            "UPDATE",
            False,
        ),
    ]

    function_rows = execute(
        """
        select
            function_definition.proname,
            pg_catalog.pg_get_userbyid(function_definition.proowner),
            function_definition.prosecdef,
            function_definition.provolatile,
            function_definition.proparallel,
            function_definition.proconfig
        from pg_catalog.pg_proc as function_definition
        where function_definition.pronamespace =
              'public'::regnamespace
          and function_definition.proname in (
              'record_security_request_attribution_event',
              'query_security_request_attribution_events',
              'cleanup_security_request_attribution_events',
              'cleanup_security_investigation_access_events'
          )
        order by function_definition.proname
        """,
        fetch=True,
    )
    assert len(function_rows) == 4
    assert all(
        row[1:] == (owner, True, "v", "u", ["search_path=pg_catalog"])
        for row in function_rows
    )

    query_acl = execute(
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
              'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)'::regprocedure
        """,
        fetch=True,
    )
    assert query_acl == [(owner, "EXECUTE", False)]

    assert execute(
        """
        select
            has_function_privilege(
                'service_role',
                'public.record_security_request_attribution_event(uuid,timestamptz,text,text,smallint,text,text,text,text,text,text,uuid)',
                'EXECUTE'
            ),
            has_function_privilege(
                'service_role',
                'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)',
                'EXECUTE'
            ),
            has_function_privilege(
                'service_role',
                'public.cleanup_security_request_attribution_events(timestamptz,integer)',
                'EXECUTE'
            ),
            has_function_privilege(
                'anon',
                'public.cleanup_security_request_attribution_events(timestamptz,integer)',
                'EXECUTE'
            ),
            has_function_privilege(
                'authenticated',
                'public.cleanup_security_request_attribution_events(timestamptz,integer)',
                'EXECUTE'
            )
        """,
        fetch=True,
    ) == [(True, False, True, False, False)]


def test_migration_repairs_rogue_acl_without_broadening_service_role() -> None:
    apply_migration()
    execute(
        """
        grant select, update on
            public.security_request_attribution_events
            to security_attribution_rogue;
        grant execute on function
            public.query_security_request_attribution_events(
                uuid, text, timestamptz, timestamptz, integer
            )
            to service_role, security_attribution_rogue;
        """
    )

    apply_migration()

    assert execute(
        """
        select
            has_table_privilege(
                'security_attribution_rogue',
                'public.security_request_attribution_events',
                'SELECT'
            ),
            has_function_privilege(
                'security_attribution_rogue',
                'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)',
                'EXECUTE'
            ),
            has_function_privilege(
                'service_role',
                'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)',
                'EXECUTE'
            ),
            has_table_privilege(
                'service_role',
                'public.security_request_attribution_events',
                'DELETE'
            )
        """,
        fetch=True,
    ) == [(False, False, False, False)]


def test_late_migration_failure_rolls_back_every_object_and_grant() -> None:
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
            to_regclass('public.security_request_attribution_events'),
            to_regclass('public.security_investigation_access_events'),
            to_regprocedure(
                'public.record_security_request_attribution_event(uuid,timestamptz,text,text,smallint,text,text,text,text,text,text,uuid)'
            ),
            to_regprocedure(
                'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)'
            )
        """,
        fetch=True,
    ) == [(None, None, None, None)]


def test_non_superuser_trusted_owner_can_apply_and_verify() -> None:
    run_sql_file_as_session("security_attribution_migrator", MIGRATION)
    run_sql_file_as_session("security_attribution_migrator", PREFLIGHT)
    run_sql_file_as_session("security_attribution_migrator", VERIFICATION)

    assert execute(
        """
        select
            pg_catalog.pg_get_userbyid(table_definition.relowner)
        from pg_catalog.pg_class as table_definition
        where table_definition.oid =
              'public.security_request_attribution_events'::regclass
        """,
        fetch=True,
    ) == [("security_attribution_migrator",)]


def test_fresh_schema_and_sequential_migration_are_equivalent() -> None:
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
    fresh_snapshot = object_snapshot()

    execute(
        """
        drop schema public cascade;
        create schema public;
        grant usage on schema public to
            service_role,
            anon,
            authenticated;
        """
    )
    apply_migration()
    sequential_snapshot = object_snapshot()

    assert fresh_snapshot == sequential_snapshot


def test_indexes_support_investigation_and_cleanup_access_paths() -> None:
    apply_migration()
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("set enable_seqscan = off")
            cursor.execute(
                """
                explain (costs off)
                select id
                from public.security_request_attribution_events
                where environment = 'development'
                  and occurred_at >= %s
                  and occurred_at < %s
                order by occurred_at, id
                limit 10000
                """,
                (cutoff, cutoff + timedelta(days=31)),
            )
            investigation_plan = "\n".join(
                row[0] for row in cursor.fetchall()
            )
            cursor.execute(
                """
                explain (costs off)
                select id
                from public.security_investigation_access_events
                where occurred_at < %s
                order by occurred_at, id
                limit 1000
                """,
                (cutoff,),
            )
            cleanup_plan = "\n".join(
                row[0] for row in cursor.fetchall()
            )

    assert "idx_security_attribution_environment_window" in (
        investigation_plan
    )
    assert "idx_security_investigation_access_cleanup" in cleanup_plan
