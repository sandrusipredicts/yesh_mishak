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
