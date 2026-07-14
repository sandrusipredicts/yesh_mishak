from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.jobs.reconcile_game_expiry import main as expiry_job_main
from app.routers.game_lifecycle import finish_expired_games, finish_game
from app.services.game_expiry_reconciliation import reconcile_expired_games
from tests.test_game_close import FakeResponse, FakeSupabaseClient


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


class FakeRpc:
    def __init__(self, responses: list[Any] | None = None, error: Exception | None = None):
        self.responses = responses or []
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, function_name: str, params: dict[str, Any]):
        self.calls.append((function_name, params))
        return self

    def execute(self):
        if self.error:
            raise self.error
        if self.responses:
            return FakeResponse([self.responses.pop(0)])
        return FakeResponse([{"scanned_count": 0, "reconciled_count": 0, "skipped_count": 0}])


def _game(
    game_id: str,
    *,
    status: str = "open",
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "id": game_id,
        "status": status,
        "expires_at": (expires_at or NOW + timedelta(hours=1)).isoformat(),
    }


def test_reconcile_expired_games_zero_candidates_is_successful_noop():
    fake = FakeRpc([{"scanned_count": 0, "reconciled_count": 0, "skipped_count": 0}])

    result = reconcile_expired_games(supabase=fake, now=NOW, batch_size=100, max_batches=5)

    assert result["scanned_count"] == 0
    assert result["reconciled_count"] == 0
    assert result["skipped_count"] == 0
    assert result["batch_count"] == 1
    assert result["reached_max_batches"] is False
    assert fake.calls == [
        (
            "reconcile_expired_games",
            {"p_cutoff": NOW.isoformat(), "p_batch_size": 100},
        )
    ]


def test_reconcile_expired_games_processes_multiple_batches():
    fake = FakeRpc(
        [
            {
                "scanned_count": 2,
                "reconciled_count": 2,
                "skipped_count": 0,
                "reconciled_game_ids": ["game-1", "game-2"],
            },
            {
                "scanned_count": 1,
                "reconciled_count": 1,
                "skipped_count": 0,
                "reconciled_game_ids": ["game-3"],
            },
        ]
    )

    result = reconcile_expired_games(supabase=fake, now=NOW, batch_size=2, max_batches=5)

    assert result["scanned_count"] == 3
    assert result["reconciled_count"] == 3
    assert result["reconciled_game_ids"] == ["game-1", "game-2", "game-3"]
    assert result["batch_count"] == 2
    assert result["reached_max_batches"] is False


def test_reconcile_expired_games_reports_max_batches_when_more_work_may_remain():
    fake = FakeRpc(
        [
            {"scanned_count": 2, "reconciled_count": 2, "skipped_count": 0},
            {"scanned_count": 2, "reconciled_count": 2, "skipped_count": 0},
        ]
    )

    result = reconcile_expired_games(supabase=fake, now=NOW, batch_size=2, max_batches=2)

    assert result["batch_count"] == 2
    assert result["reached_max_batches"] is True


def test_reconcile_expired_games_rejects_invalid_batch_arguments():
    with pytest.raises(ValueError):
        reconcile_expired_games(supabase=FakeRpc(), batch_size=0)

    with pytest.raises(ValueError):
        reconcile_expired_games(supabase=FakeRpc(), max_batches=0)


def test_cli_returns_zero_and_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        "app.jobs.reconcile_game_expiry.reconcile_expired_games",
        lambda batch_size, max_batches: {
            "scanned_count": 1,
            "reconciled_count": 1,
            "skipped_count": 0,
        },
    )

    exit_code = expiry_job_main(["--batch-size", "10", "--max-batches", "2"])

    assert exit_code == 0
    assert '"reconciled_count": 1' in capsys.readouterr().out


def test_cli_returns_nonzero_on_failure(monkeypatch):
    def fail(**_: Any):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.jobs.reconcile_game_expiry.reconcile_expired_games", fail)

    assert expiry_job_main([]) == 1


def test_lazy_finish_game_uses_conditional_expiry_update():
    tables = {
        "games": [
            _game("past", expires_at=NOW - timedelta(minutes=1)),
            _game("future", expires_at=NOW + timedelta(minutes=1)),
            _game("finished", status="finished", expires_at=NOW - timedelta(minutes=1)),
            _game("cancelled", status="cancelled", expires_at=NOW - timedelta(minutes=1)),
        ]
    }
    fake = FakeSupabaseClient(tables)

    assert finish_game("past", fake, cutoff=NOW)["status"] == "finished"
    assert finish_game("future", fake, cutoff=NOW) is None
    assert finish_game("finished", fake, cutoff=NOW) is None
    assert finish_game("cancelled", fake, cutoff=NOW) is None

    assert tables["games"][0]["status"] == "finished"
    assert tables["games"][1]["status"] == "open"
    assert tables["games"][2]["status"] == "finished"
    assert tables["games"][3]["status"] == "cancelled"


def test_finish_expired_games_transitions_past_due_active_only():
    tables = {
        "games": [
            _game("past", expires_at=NOW),
            _game("future", expires_at=NOW + timedelta(seconds=1)),
            _game("cancelled", status="cancelled", expires_at=NOW - timedelta(hours=1)),
        ]
    }
    fake = FakeSupabaseClient(tables)

    active = finish_expired_games(tables["games"], supabase=fake, now=NOW)

    assert [game["id"] for game in active] == ["future"]
    assert tables["games"][0]["status"] == "finished"
    assert tables["games"][1]["status"] == "open"
    assert tables["games"][2]["status"] == "cancelled"


def test_reconciliation_migration_defines_conditional_locked_batch():
    repo_root = Path(__file__).resolve().parents[2]
    migration = (repo_root / "backend/migrations/game_expiry_reconciliation.sql").read_text(
        encoding="utf-8",
    )

    assert "for update skip locked" in migration.lower()
    assert "g.status in ('open', 'full')" in migration
    assert "g.expires_at <= p_cutoff" in migration
    assert "idx_games_expiry_reconciliation" in migration
