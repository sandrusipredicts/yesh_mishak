from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION = (BACKEND_DIR / "migrations" / "google_identity_resolution.sql").read_text()
MONOTONIC_MIGRATION = (BACKEND_DIR / "migrations" / "token_revocation_monotonic.sql").read_text()
SCHEMA = (BACKEND_DIR / "schema.sql").read_text()


def test_identity_schema_keeps_required_unique_constraints_and_foreign_key() -> None:
    assert "user_id uuid not null references users(id) on delete cascade" in SCHEMA
    assert "unique (provider, provider_subject)" in SCHEMA
    assert "unique (user_id, provider)" in SCHEMA


def test_identity_migration_stops_for_ambiguous_production_data() -> None:
    assert "Duplicate (provider, provider_subject) rows require manual repair" in MIGRATION
    assert "Multiple identities for one user/provider require manual repair" in MIGRATION
    assert "Case-insensitive duplicate user emails require manual repair" in MIGRATION
    assert "A user has conflicting legacy and canonical Google subjects" in MIGRATION


def test_google_login_resolution_is_atomic_locked_and_service_role_only() -> None:
    resolver = MIGRATION.split("create or replace function public.resolve_google_login", 1)[1]
    resolver = resolver.split("create or replace function public.link_google_identity", 1)[0]

    assert "pg_advisory_xact_lock" in resolver
    assert "insert into public.users" in resolver
    assert "insert into public.user_identities" in resolver
    assert "exception when unique_violation" in resolver
    assert "account_link_required" in resolver
    assert "revoke all on function public.resolve_google_login" in MIGRATION
    assert "grant execute on function public.resolve_google_login" in MIGRATION


def test_settings_link_is_idempotent_and_does_not_revoke_sessions() -> None:
    linker = MIGRATION.split("create or replace function public.link_google_identity", 1)[1]

    assert "already_linked_same" in linker
    assert "email_conflict_other_user" in linker
    assert "tokens_valid_after" not in linker
    assert "pg_advisory_xact_lock" in linker

    later_linker = MONOTONIC_MIGRATION.split(
        "create or replace function public.link_google_identity", 1
    )[1].split("create or replace function public.unlink_google_identity", 1)[0]
    assert "already_linked_same" in later_linker
    assert "email_conflict_other_user" in later_linker
    assert "tokens_valid_after" not in later_linker
