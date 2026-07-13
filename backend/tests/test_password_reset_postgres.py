"""Real PostgreSQL validation for the password-reset migration and RPCs.

Set PASSWORD_RESET_DATABASE_URL to a disposable database. These tests destroy
and recreate the public schema and must never run against a shared database.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

DATABASE_URL = os.getenv("PASSWORD_RESET_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="PASSWORD_RESET_DATABASE_URL is not configured")
MIGRATION = Path(__file__).parents[1] / "migrations" / "password_reset_tokens.sql"
MONOTONIC_REVOCATION_MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "token_revocation_monotonic.sql"
)


def execute(sql: str, params: tuple = (), *, fetch: bool = False):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params if params else None)
            return cursor.fetchall() if fetch else None


@pytest.fixture(scope="module", autouse=True)
def migrated_database():
    execute("drop schema if exists public cascade; create schema public")
    execute("do $$ begin create role anon nologin; exception when duplicate_object then null; end $$")
    execute("do $$ begin create role authenticated nologin; exception when duplicate_object then null; end $$")
    execute("do $$ begin create role service_role nologin bypassrls; exception when duplicate_object then null; end $$")
    execute("""
        create table public.users (
            id uuid primary key,
            email text not null unique,
            password_hash text,
            tokens_valid_after timestamptz
        )
    """)
    execute(MIGRATION.read_text(encoding="utf-8"))
    # E01-05: apply the monotonic-revocation redefinition on top. Its
    # account-linking functions reference public.user_identities, which
    # this minimal schema does not create; that's fine, plpgsql only
    # validates those references lazily on first invocation, and this file
    # never calls those functions.
    execute(MONOTONIC_REVOCATION_MIGRATION.read_text(encoding="utf-8"))
    yield


@pytest.fixture(autouse=True)
def clean_rows():
    execute("truncate public.password_reset_tokens, public.password_reset_rate_limits, public.password_reset_email_cooldowns, public.users cascade")


def add_user() -> str:
    user_id = str(uuid4())
    execute("insert into public.users(id,email,password_hash) values (%s,%s,'old-hash')", (user_id, f"{user_id}@example.com"))
    return user_id


def rpc(sql: str, params: tuple = ()):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("set role service_role")
            cursor.execute(sql, params if params else None)
            return cursor.fetchall()


def create_token(user_id: str, token_hash: str):
    return rpc("select * from public.create_password_reset_token(%s,%s,30)", (user_id, token_hash))


def test_function_signatures_rls_and_grants():
    signatures = execute("""
        select p.proname, pg_catalog.pg_get_function_identity_arguments(p.oid)
        from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public' and p.proname like '%password_reset%'
    """, fetch=True)
    assert len(signatures) == 6
    rls = execute("""
        select relname,relrowsecurity from pg_catalog.pg_class
        where oid in ('public.password_reset_tokens'::regclass,
                      'public.password_reset_rate_limits'::regclass,
                      'public.password_reset_email_cooldowns'::regclass)
        order by relname
    """, fetch=True)
    assert all(enabled for _, enabled in rls) and len(rls) == 3
    table_privileges = execute("""
        select bool_or(has_table_privilege('anon',c.oid,'SELECT')),
               bool_or(has_table_privilege('authenticated',c.oid,'SELECT'))
        from pg_catalog.pg_class c
        where c.oid in ('public.password_reset_tokens'::regclass,
                        'public.password_reset_rate_limits'::regclass,
                        'public.password_reset_email_cooldowns'::regclass)
    """, fetch=True)
    assert table_privileges == [(False, False)]
    privileges = execute("""
        select bool_and(has_function_privilege('service_role',p.oid,'EXECUTE')),
               bool_or(has_function_privilege('anon',p.oid,'EXECUTE')),
               bool_or(has_function_privilege('authenticated',p.oid,'EXECUTE'))
        from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public' and p.proname like '%password_reset%'
    """, fetch=True)
    assert privileges == [(True, False, False)]


def test_concurrent_creation_leaves_one_usable_token():
    user_id = add_user()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda value: create_token(user_id, value), ("hash-a", "hash-b")))
    rows = execute("select status,count(*) from public.password_reset_tokens group by status order by status", fetch=True)
    assert rows == [("invalidated", 1), ("pending_delivery", 1)]


def test_late_delivery_cannot_activate_superseded_token():
    user_id = add_user()
    create_token(user_id, "hash-a")
    create_token(user_id, "hash-b")
    assert rpc("select * from public.finalize_password_reset_delivery('hash-a',true)") == [("unchanged", False)]
    assert rpc("select * from public.finalize_password_reset_delivery('hash-b',true)") == [("active", True)]
    assert execute("select token_hash,status from public.password_reset_tokens order by token_hash", fetch=True) == [("hash-a", "invalidated"), ("hash-b", "active")]


def test_concurrent_delivery_finalization_activates_once():
    user_id = add_user(); create_token(user_id, "hash-a")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rpc("select * from public.finalize_password_reset_delivery('hash-a',true)"), range(2)))
    assert sorted(results) == [[("active", True)], [("unchanged", False)]]


def test_concurrent_consumption_updates_once_and_uses_database_time():
    user_id = add_user(); create_token(user_id, "hash-a")
    rpc("select * from public.finalize_password_reset_delivery('hash-a',true)")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda password: rpc("select * from public.consume_password_reset_token('hash-a',%s)", (password,)), ("new-a", "new-b")))
    statuses = sorted(result[0][0] for result in results)
    assert statuses == ["consumed", "success"]
    assert execute("select tokens_valid_after is not null from public.users where id=%s", (user_id,), fetch=True) == [(True,)]


def test_rolling_cooldown_blocks_bucket_boundary_and_reports_retry_after():
    assert rpc("select public.check_password_reset_request_rate_limit('email-key','ip-key')")[0][0]["allowed"] is True
    # Models 12:04:59 then 12:05:01: 298 seconds of the rolling cooldown remain.
    execute("update public.password_reset_email_cooldowns set last_attempt_at=now()-interval '2 seconds', next_allowed_at=now()+interval '298 seconds' where key_hash='email-key'")
    result = rpc("select public.check_password_reset_request_rate_limit('email-key','ip-key')")[0][0]
    assert result["allowed"] is False
    assert result["scope"] == "email_cooldown"
    assert 297 <= result["retry_after_seconds"] <= 298


def test_concurrent_cooldown_allows_only_one_request():
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rpc("select public.check_password_reset_request_rate_limit('same-email','ip-key')")[0][0], range(2)))
    assert sorted(result["allowed"] for result in results) == [False, True]


def test_consume_rolls_back_user_update_when_token_update_fails():
    user_id = add_user(); create_token(user_id, "hash-a")
    rpc("select * from public.finalize_password_reset_delivery('hash-a',true)")
    execute("""
        create function public.fail_consumption() returns trigger language plpgsql as $$
        begin if new.status='consumed' then raise exception 'forced failure'; end if; return new; end $$;
        create trigger fail_consumption before update on public.password_reset_tokens for each row execute function public.fail_consumption()
    """)
    with pytest.raises(psycopg.Error):
        rpc("select * from public.consume_password_reset_token('hash-a','new-hash')")


# ---- E01-05: tokens_valid_after must never move backward ------------------


def test_consume_password_reset_token_does_not_move_tokens_valid_after_backward():
    """A later revocation (e.g. a concurrent logout on another
    worker/device) may already have advanced tokens_valid_after into the
    future relative to this reset confirmation. Consuming the reset token
    must not roll that back."""
    user_id = add_user(); create_token(user_id, "hash-a")
    rpc("select * from public.finalize_password_reset_delivery('hash-a',true)")
    execute(
        "update public.users set tokens_valid_after = now() + interval '1 hour' where id=%s",
        (user_id,),
    )
    rpc("select * from public.consume_password_reset_token('hash-a','new-hash')")
    remaining = execute(
        "select tokens_valid_after > now() + interval '59 minutes' from public.users where id=%s",
        (user_id,),
        fetch=True,
    )
    assert remaining == [(True,)]


def test_revoke_user_tokens_does_not_move_tokens_valid_after_backward():
    user_id = add_user()
    execute(
        "update public.users set tokens_valid_after = now() + interval '1 hour' where id=%s",
        (user_id,),
    )
    result = rpc("select * from public.revoke_user_tokens(%s)", (user_id,))
    assert result == [("revoked",)]
    remaining = execute(
        "select tokens_valid_after > now() + interval '59 minutes' from public.users where id=%s",
        (user_id,),
        fetch=True,
    )
    assert remaining == [(True,)]


def test_revoke_user_tokens_advances_from_null():
    user_id = add_user()
    before = execute("select now()", fetch=True)[0][0]
    result = rpc("select * from public.revoke_user_tokens(%s)", (user_id,))
    assert result == [("revoked",)]
    after = execute("select now()", fetch=True)[0][0]
    value = execute(
        "select tokens_valid_after from public.users where id=%s", (user_id,), fetch=True
    )[0][0]
    assert before <= value <= after


def test_revoke_user_tokens_missing_user():
    result = rpc("select * from public.revoke_user_tokens(%s)", (str(uuid4()),))
    assert result == [("user_not_found",)]
    assert execute("select password_hash from public.users where id=%s", (user_id,), fetch=True) == [("old-hash",)]
    assert execute("select status from public.password_reset_tokens where token_hash='hash-a'", fetch=True) == [("active",)]
    execute("drop trigger fail_consumption on public.password_reset_tokens; drop function public.fail_consumption()")
