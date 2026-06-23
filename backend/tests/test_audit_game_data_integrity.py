"""Tests for game data integrity audit (ISSUE-050)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from scripts.audit_game_data_integrity import Finding, run_audit


NOW = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(hours=6)
FUTURE = NOW + timedelta(hours=6)


def _user(uid: str = "user-1") -> dict[str, Any]:
    return {"id": uid}


def _field(
    fid: str = "field-1",
    *,
    status: str = "open",
    approval_status: str = "approved",
    verified: bool = True,
) -> dict[str, Any]:
    return {
        "id": fid,
        "name": "Test Field",
        "status": status,
        "approval_status": approval_status,
        "verified": verified,
        "sport_type": "football",
    }


def _game(
    gid: str = "game-1",
    *,
    field_id: str = "field-1",
    created_by: str = "user-1",
    status: str = "open",
    players_present: int = 2,
    max_players: int = 10,
    scheduled_at: str | None = None,
    created_at: str | None = None,
    started_at: str | None = None,
    cancelled_at: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    base = {
        "id": gid,
        "field_id": field_id,
        "created_by": created_by,
        "sport_type": "football",
        "status": status,
        "players_present": players_present,
        "max_players": max_players,
        "scheduled_at": scheduled_at,
        "created_at": created_at or NOW.isoformat(),
        "started_at": started_at or NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
        "cancelled_at": cancelled_at,
    }
    base.update(overrides)
    return base


def _gp(game_id: str, user_id: str, gp_id: str | None = None) -> dict[str, Any]:
    return {
        "id": gp_id or f"gp-{game_id}-{user_id}",
        "game_id": game_id,
        "user_id": user_id,
        "joined_at": NOW.isoformat(),
    }


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data

    def select(self, _columns: str) -> "FakeQuery":
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse(self._data)


class FakeAuditSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.tables.get(name, []))


def _run(
    *,
    games: list[dict] | None = None,
    fields: list[dict] | None = None,
    users: list[dict] | None = None,
    game_players: list[dict] | None = None,
) -> list[Finding]:
    fake = FakeAuditSupabase(
        {
            "games": games if games is not None else [_game()],
            "fields": fields if fields is not None else [_field()],
            "users": users if users is not None else [_user()],
            "game_players": game_players if game_players is not None else [_gp("game-1", "user-1")],
        }
    )
    return run_audit(fake)


# ═══════════════════════════════════════════════════════════
# Clean data
# ═══════════════════════════════════════════════════════════


def test_clean_data_returns_no_critical_findings():
    findings = _run(
        games=[_game(players_present=1)],
        game_players=[_gp("game-1", "user-1")],
    )
    critical = [f for f in findings if f.severity == "critical"]
    assert critical == []


# ═══════════════════════════════════════════════════════════
# 1. Games without valid fields
# ═══════════════════════════════════════════════════════════


def test_null_field_id_detected():
    findings = _run(games=[_game(field_id=None)])
    matches = [f for f in findings if f.check == "games_without_valid_fields"]
    assert len(matches) == 1
    assert matches[0].severity == "critical"
    assert "null" in matches[0].reason


def test_missing_field_detected():
    findings = _run(
        games=[_game(field_id="missing-field")],
        fields=[_field("other-field")],
    )
    matches = [f for f in findings if f.check == "games_without_valid_fields"]
    assert len(matches) == 1
    assert matches[0].severity == "critical"
    assert "missing" in matches[0].reason


# ═══════════════════════════════════════════════════════════
# 2. Games without valid creators
# ═══════════════════════════════════════════════════════════


def test_null_creator_detected():
    findings = _run(games=[_game(created_by=None)])
    matches = [f for f in findings if f.check == "games_without_valid_creators"]
    assert len(matches) == 1
    assert matches[0].severity == "critical"


def test_missing_creator_detected():
    findings = _run(
        games=[_game(created_by="ghost-user")],
        users=[_user("other-user")],
    )
    matches = [f for f in findings if f.check == "games_without_valid_creators"]
    assert len(matches) == 1
    assert "does not exist" in matches[0].reason


# ═══════════════════════════════════════════════════════════
# 3. Invalid status
# ═══════════════════════════════════════════════════════════


def test_invalid_status_detected():
    findings = _run(games=[_game(status="legacy_active")])
    matches = [f for f in findings if f.check == "invalid_game_status"]
    assert len(matches) == 1
    assert matches[0].severity == "critical"


def test_valid_statuses_not_flagged():
    for s in ["open", "full", "finished", "cancelled"]:
        findings = _run(games=[_game(status=s, cancelled_at=NOW.isoformat() if s == "cancelled" else None)])
        matches = [f for f in findings if f.check == "invalid_game_status"]
        assert matches == [], f"status={s} should not be flagged"


# ═══════════════════════════════════════════════════════════
# 4. Invalid participant counts
# ═══════════════════════════════════════════════════════════


def test_negative_players_present_detected():
    findings = _run(games=[_game(players_present=-1)])
    matches = [f for f in findings if f.check == "invalid_participant_counts" and "negative" in f.reason]
    assert len(matches) == 1
    assert matches[0].severity == "critical"


def test_players_present_exceeds_max_detected():
    findings = _run(games=[_game(players_present=11, max_players=10)])
    matches = [f for f in findings if f.check == "invalid_participant_counts" and "exceeds" in f.reason]
    assert len(matches) == 1


def test_max_players_zero_detected():
    findings = _run(games=[_game(max_players=0)])
    matches = [f for f in findings if f.check == "invalid_participant_counts" and "<= 0" in f.reason]
    assert len(matches) == 1


# ═══════════════════════════════════════════════════════════
# 5. Status/count contradictions
# ═══════════════════════════════════════════════════════════


def test_full_but_under_capacity_detected():
    findings = _run(games=[_game(status="full", players_present=3, max_players=10)])
    matches = [f for f in findings if f.check == "status_count_contradictions"]
    assert len(matches) == 1
    assert "full" in matches[0].reason


def test_open_but_at_capacity_detected():
    findings = _run(games=[_game(status="open", players_present=10, max_players=10)])
    matches = [f for f in findings if f.check == "status_count_contradictions"]
    assert len(matches) == 1
    assert "open" in matches[0].reason


# ═══════════════════════════════════════════════════════════
# 6. Games on inactive fields
# ═══════════════════════════════════════════════════════════


def test_active_game_on_closed_field_detected():
    findings = _run(
        games=[_game(status="open")],
        fields=[_field(status="closed")],
    )
    matches = [f for f in findings if f.check == "games_on_inactive_fields"]
    assert any("closed" in m.reason for m in matches)


def test_active_game_on_renovation_field_detected():
    findings = _run(
        games=[_game(status="open")],
        fields=[_field(status="renovation")],
    )
    matches = [f for f in findings if f.check == "games_on_inactive_fields"]
    assert any("renovation" in m.reason for m in matches)


def test_active_game_on_unapproved_field_detected():
    findings = _run(
        games=[_game(status="open")],
        fields=[_field(approval_status="pending")],
    )
    matches = [f for f in findings if f.check == "games_on_inactive_fields"]
    assert any("pending" in m.reason for m in matches)


def test_active_game_on_unverified_field_detected():
    findings = _run(
        games=[_game(status="open")],
        fields=[_field(verified=False)],
    )
    matches = [f for f in findings if f.check == "games_on_inactive_fields"]
    assert any("unverified" in m.reason for m in matches)


def test_finished_game_on_closed_field_not_flagged():
    findings = _run(
        games=[_game(status="finished")],
        fields=[_field(status="closed")],
    )
    matches = [f for f in findings if f.check == "games_on_inactive_fields"]
    assert matches == []


# ═══════════════════════════════════════════════════════════
# 7. Scheduled game inconsistencies
# ═══════════════════════════════════════════════════════════


def test_scheduled_in_past_but_active_detected():
    findings = _run(
        games=[_game(status="open", scheduled_at=PAST.isoformat())],
    )
    matches = [f for f in findings if f.check == "scheduled_game_inconsistencies"]
    assert len(matches) == 1
    assert matches[0].severity == "info"


def test_scheduled_in_future_not_flagged():
    far_future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    findings = _run(
        games=[_game(status="open", scheduled_at=far_future, players_present=1)],
        game_players=[_gp("game-1", "user-1")],
    )
    matches = [f for f in findings if f.check == "scheduled_game_inconsistencies"]
    assert matches == []


# ═══════════════════════════════════════════════════════════
# 8. Participant table inconsistencies
# ═══════════════════════════════════════════════════════════


def test_players_present_mismatch_detected():
    findings = _run(
        games=[_game(status="open", players_present=5)],
        game_players=[_gp("game-1", "user-1"), _gp("game-1", "user-2")],
        users=[_user("user-1"), _user("user-2")],
    )
    matches = [f for f in findings if f.check == "participant_table_inconsistencies" and "match" in f.reason]
    assert len(matches) == 1
    assert matches[0].data["players_present"] == 5
    assert matches[0].data["actual_rows"] == 2


def test_orphaned_game_player_detected():
    findings = _run(
        games=[],
        game_players=[_gp("nonexistent-game", "user-1")],
    )
    matches = [f for f in findings if f.check == "participant_table_inconsistencies" and "missing game" in f.reason]
    assert len(matches) == 1
    assert matches[0].severity == "critical"


def test_game_player_missing_user_detected():
    findings = _run(
        games=[_game()],
        game_players=[_gp("game-1", "ghost-user")],
        users=[_user("user-1")],
    )
    matches = [f for f in findings if f.check == "participant_table_inconsistencies" and "missing user" in f.reason]
    assert len(matches) == 1


def test_duplicate_game_player_detected():
    findings = _run(
        games=[_game(players_present=1)],
        game_players=[
            _gp("game-1", "user-1", gp_id="gp-1"),
            _gp("game-1", "user-1", gp_id="gp-2"),
        ],
    )
    matches = [f for f in findings if f.check == "participant_table_inconsistencies" and "duplicate" in f.reason]
    assert len(matches) == 1


# ═══════════════════════════════════════════════════════════
# 9. Timestamp checks
# ═══════════════════════════════════════════════════════════


def test_missing_created_at_detected():
    game = _game()
    game["created_at"] = None
    findings = _run(games=[game])
    matches = [f for f in findings if f.check == "time_data_sanity" and "created_at" in f.reason]
    assert len(matches) == 1


def test_cancelled_without_cancelled_at_detected():
    findings = _run(games=[_game(status="cancelled", cancelled_at=None)])
    matches = [f for f in findings if f.check == "time_data_sanity" and "cancelled_at" in f.reason]
    assert len(matches) == 1


# ═══════════════════════════════════════════════════════════
# Multiple issues on one game
# ═══════════════════════════════════════════════════════════


def test_multiple_issues_all_detected():
    bad_game = _game(
        field_id="missing-field",
        created_by=None,
        status="bogus",
        players_present=-1,
        max_players=0,
    )
    findings = _run(
        games=[bad_game],
        fields=[_field()],
    )
    checks = {f.check for f in findings}
    assert "games_without_valid_fields" in checks
    assert "games_without_valid_creators" in checks
    assert "invalid_game_status" in checks
    assert "invalid_participant_counts" in checks
