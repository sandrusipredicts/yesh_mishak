from pathlib import Path


MIGRATION = Path(__file__).parents[1] / "migrations" / "email_verification.sql"


def test_migration_stores_only_token_hash_and_lifecycle_timestamps() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "token_hash text not null unique" in sql
    assert "expires_at timestamptz not null" in sql
    assert "used_at timestamptz" in sql
    assert " token text" not in sql


def test_migration_grandfathers_only_rows_without_verification_policy() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "where email_verified is null" in sql
    assert "alter column email_verified set not null" in sql


def test_verification_function_locks_and_consumes_token_atomically() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "for update" in sql
    assert "if token_row.used_at is not null" in sql
    assert "update email_verification_tokens set used_at = now()" in sql
    assert "update users" in sql


def test_verification_function_is_service_role_only() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "revoke all on function verify_email_token(text) from public, anon, authenticated" in sql
    assert "grant execute on function verify_email_token(text) to service_role" in sql


def test_resend_cooldown_is_atomic_across_workers_and_invalidates_old_token() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "pg_advisory_xact_lock" in sql
    assert "prepare_email_verification_token" in sql
    assert "return 'cooldown'" in sql
    assert "set used_at = now()" in sql
    assert "where user_id = p_user_id and used_at is null" in sql


def test_prepare_token_rpc_cannot_be_called_by_public_roles() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "prepare_email_verification_token(uuid, text, timestamptz, integer)" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
