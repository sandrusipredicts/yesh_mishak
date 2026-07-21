"""Real PostgreSQL checks for the E09-02 rollout SQL.

Set ANALYTICS_EVENTS_DATABASE_URL to a disposable database. These tests destroy
and recreate the public schema and must never run against a shared database.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest

psycopg = pytest.importorskip("psycopg")

DATABASE_URL = os.getenv("ANALYTICS_EVENTS_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="ANALYTICS_EVENTS_DATABASE_URL is not configured",
)
BACKEND_DIR = Path(__file__).parents[1]
API_METRICS_MIGRATION = BACKEND_DIR / "migrations" / "api_request_metrics.sql"
ANALYTICS_MIGRATION = BACKEND_DIR / "migrations" / "analytics_events.sql"
PREFLIGHT = BACKEND_DIR / "scripts" / "analytics_events_migration_preflight.sql"
VERIFICATION = BACKEND_DIR / "scripts" / "verify_analytics_events_migration.sql"


def execute(sql: str, params: tuple = (), *, fetch: bool = False):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params if params else None)
            return cursor.fetchall() if fetch else None


def run_sql_file(path: Path) -> None:
    execute(path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def clean_database() -> None:
    execute(
        """
        drop schema if exists public cascade;
        create schema public;
        do $$
        begin
            create role service_role nologin bypassrls;
        exception when duplicate_object then
            null;
        end
        $$;
        grant usage on schema public to service_role;
        """
    )


def apply_prerequisite() -> None:
    run_sql_file(API_METRICS_MIGRATION)


def apply_analytics_migration() -> None:
    run_sql_file(ANALYTICS_MIGRATION)


def test_preflight_enforces_api_metrics_migration_order() -> None:
    with pytest.raises(psycopg.errors.RaiseException, match="api_request_metrics.sql"):
        run_sql_file(PREFLIGHT)

    apply_prerequisite()
    run_sql_file(PREFLIGHT)


def test_preflight_rejects_partial_analytics_state() -> None:
    apply_prerequisite()
    execute("create table public.analytics_events (id uuid primary key)")

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="partial analytics migration state",
    ):
        run_sql_file(PREFLIGHT)


def test_verification_exercises_migration_and_rolls_back_test_event() -> None:
    apply_prerequisite()
    apply_analytics_migration()
    execute(
        """
        insert into public.analytics_events (
            id, event_name, platform, app_version, properties
        )
        values (
            '00000000-0000-4000-8000-000000000001',
            'app_open',
            'android',
            'existing-row',
            '{}'::jsonb
        )
        """
    )

    run_sql_file(PREFLIGHT)
    apply_analytics_migration()
    run_sql_file(VERIFICATION)

    rows = execute(
        "select id, app_version from public.analytics_events order by id",
        fetch=True,
    )
    assert rows == [
        (UUID("00000000-0000-4000-8000-000000000001"), "existing-row")
    ]


def test_verification_rejects_missing_service_role_grant() -> None:
    apply_prerequisite()
    apply_analytics_migration()
    execute("revoke delete on public.analytics_events from service_role")

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="direct SELECT, INSERT, and DELETE",
    ):
        run_sql_file(VERIFICATION)


def test_verification_rejects_missing_check_constraints() -> None:
    apply_prerequisite()
    apply_analytics_migration()
    execute(
        """
        do $$
        declare
            constraint_name name;
        begin
            for constraint_name in
                select conname
                from pg_catalog.pg_constraint
                where conrelid = 'public.analytics_events'::regclass
                  and contype = 'c'
            loop
                execute format(
                    'alter table public.analytics_events drop constraint %I',
                    constraint_name
                );
            end loop;
        end
        $$
        """
    )

    with pytest.raises(psycopg.errors.RaiseException, match="CHECK constraints are missing"):
        run_sql_file(VERIFICATION)
