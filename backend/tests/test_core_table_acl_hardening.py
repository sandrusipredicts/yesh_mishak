"""Static contract checks for Issue #917 core-table ACL hardening."""

from __future__ import annotations

import re
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_SQL = (
    BACKEND_DIR / "migrations" / "core_table_acl_hardening.sql"
).read_text(encoding="utf-8")
SCHEMA_SQL = (BACKEND_DIR / "schema.sql").read_text(encoding="utf-8")

EXPECTED_TABLES = {
    "public.users",
    "public.fields",
    "public.games",
    "public.field_reports",
    "public.user_moderation_audit",
}
EXPECTED_ROLES = {"anon", "authenticated"}
EXPECTED_PRIVILEGES = {"truncate", "trigger", "references"}


def _without_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _hardening_revoke(sql: str) -> tuple[set[str], set[str], set[str]]:
    match = re.search(
        r"revoke\s+(.*?)\s+on\s+table\s+(.*?)\s+from\s+(.*?);",
        _without_comments(sql),
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, "core-table dangerous-privilege REVOKE was not found"

    privileges = {
        value.strip().lower() for value in match.group(1).split(",")
    }
    tables = {value.strip().lower() for value in match.group(2).split(",")}
    roles = {value.strip().lower() for value in match.group(3).split(",")}
    return privileges, tables, roles


def test_migration_revokes_only_the_approved_privilege_matrix() -> None:
    privileges, tables, roles = _hardening_revoke(MIGRATION_SQL)

    assert privileges == EXPECTED_PRIVILEGES
    assert tables == EXPECTED_TABLES
    assert roles == EXPECTED_ROLES


def test_migration_is_transactional_and_idempotent_sql() -> None:
    statements = [
        re.sub(r"\s+", " ", statement).strip().lower()
        for statement in _without_comments(MIGRATION_SQL).split(";")
        if statement.strip()
    ]

    assert statements[0] == "begin"
    assert statements[-1] == "commit"
    assert len([statement for statement in statements if statement.startswith("revoke ")]) == 1


def test_migration_does_not_change_row_dml_or_rls_policy_contracts() -> None:
    executable_sql = _without_comments(MIGRATION_SQL).lower()

    for privilege in ("select", "insert", "update", "delete"):
        assert privilege not in executable_sql
    assert "create policy" not in executable_sql
    assert "drop policy" not in executable_sql
    assert "row level security" not in executable_sql
    assert " grant " not in f" {executable_sql} "


def test_fresh_schema_contains_the_same_acl_hardening_contract() -> None:
    assert _hardening_revoke(SCHEMA_SQL) == _hardening_revoke(MIGRATION_SQL)
