from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.jobs.reconcile_game_expiry import main as expiry_job_main
from app.routers.game_lifecycle import finish_expired_games, finish_game
from app.services.game_expiry_reconciliation import reconcile_expired_games
from app.services.job_runs import JobRun, sanitize_error_message
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


class FakeJobRunRecorder:
    def __init__(
        self,
        *,
        start_error: Exception | None = None,
        success_error: Exception | None = None,
        failure_error: Exception | None = None,
    ) -> None:
        self.start_error = start_error
        self.success_error = success_error
        self.failure_error = failure_error
        self.started: list[dict[str, Any]] = []
        self.succeeded: list[tuple[JobRun, dict[str, Any]]] = []
        self.failed: list[tuple[JobRun, BaseException]] = []
        self.job_run = JobRun(
            id="job-run-1",
            job_name="game_expiry_reconciliation",
            started_at=NOW,
            start_monotonic=0.0,
        )

    def start(self, *, job_name: str, metadata: dict[str, Any] | None = None) -> JobRun:
        self.started.append({"job_name": job_name, "metadata": metadata or {}})
        if self.start_error:
            raise self.start_error
        return self.job_run

    def mark_succeeded(self, job_run: JobRun, result: dict[str, Any]) -> None:
        self.succeeded.append((job_run, result))
        if self.success_error:
            raise self.success_error

    def mark_failed(self, job_run: JobRun, exc: BaseException) -> None:
        self.failed.append((job_run, exc))
        if self.failure_error:
            raise self.failure_error


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


def test_cli_records_successful_invocation_once(monkeypatch):
    recorder = FakeJobRunRecorder()
    result = {
        "scanned_count": 4,
        "reconciled_count": 3,
        "skipped_count": 1,
        "failed_count": 0,
        "batch_count": 2,
        "reached_max_batches": False,
    }
    monkeypatch.setattr("app.jobs.reconcile_game_expiry.JobRunRecorder", lambda: recorder)
    monkeypatch.setattr(
        "app.jobs.reconcile_game_expiry.reconcile_expired_games",
        lambda batch_size, max_batches: result,
    )

    assert expiry_job_main(["--batch-size", "2", "--max-batches", "5"]) == 0

    assert recorder.started == [
        {
            "job_name": "game_expiry_reconciliation",
            "metadata": {
                "batch_size": 2,
                "max_batches": 5,
                "entry_point": "app.jobs.reconcile_game_expiry",
            },
        }
    ]
    assert recorder.succeeded == [(recorder.job_run, result)]
    assert recorder.failed == []


def test_cli_records_zero_work_success(monkeypatch):
    recorder = FakeJobRunRecorder()
    result = {
        "scanned_count": 0,
        "reconciled_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "batch_count": 1,
        "reached_max_batches": False,
    }
    monkeypatch.setattr("app.jobs.reconcile_game_expiry.JobRunRecorder", lambda: recorder)
    monkeypatch.setattr(
        "app.jobs.reconcile_game_expiry.reconcile_expired_games",
        lambda batch_size, max_batches: result,
    )

    assert expiry_job_main([]) == 0
    assert len(recorder.succeeded) == 1
    assert recorder.succeeded[0][1]["reconciled_count"] == 0


def test_cli_multiple_batches_still_records_one_invocation(monkeypatch):
    recorder = FakeJobRunRecorder()
    monkeypatch.setattr("app.jobs.reconcile_game_expiry.JobRunRecorder", lambda: recorder)
    monkeypatch.setattr(
        "app.jobs.reconcile_game_expiry.reconcile_expired_games",
        lambda batch_size, max_batches: {
            "scanned_count": 200,
            "reconciled_count": 200,
            "skipped_count": 0,
            "failed_count": 0,
            "batch_count": 2,
            "reached_max_batches": False,
        },
    )

    assert expiry_job_main(["--batch-size", "100", "--max-batches", "50"]) == 0
    assert len(recorder.started) == 1
    assert len(recorder.succeeded) == 1
    assert recorder.succeeded[0][1]["batch_count"] == 2


def test_cli_returns_nonzero_on_failure(monkeypatch):
    def fail(**_: Any):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.jobs.reconcile_game_expiry.reconcile_expired_games", fail)

    assert expiry_job_main([]) == 1


def test_cli_records_failed_invocation_and_preserves_nonzero(monkeypatch):
    recorder = FakeJobRunRecorder()

    def fail(**_: Any):
        raise RuntimeError("database unavailable password=secret-value")

    monkeypatch.setattr("app.jobs.reconcile_game_expiry.JobRunRecorder", lambda: recorder)
    monkeypatch.setattr("app.jobs.reconcile_game_expiry.reconcile_expired_games", fail)

    assert expiry_job_main([]) == 1
    assert len(recorder.failed) == 1
    assert isinstance(recorder.failed[0][1], RuntimeError)
    assert recorder.succeeded == []


def test_cli_monitoring_start_failure_does_not_prevent_reconciliation(monkeypatch):
    recorder = FakeJobRunRecorder(start_error=RuntimeError("job_runs table missing"))
    attempted = {"value": False}

    def reconcile(**_: Any):
        attempted["value"] = True
        return {"scanned_count": 0, "reconciled_count": 0, "skipped_count": 0}

    monkeypatch.setattr("app.jobs.reconcile_game_expiry.JobRunRecorder", lambda: recorder)
    monkeypatch.setattr("app.jobs.reconcile_game_expiry.reconcile_expired_games", reconcile)

    assert expiry_job_main([]) == 0
    assert attempted["value"] is True
    assert recorder.succeeded == []


def test_cli_success_finalization_failure_preserves_success(monkeypatch, caplog):
    recorder = FakeJobRunRecorder(success_error=TimeoutError("timeout"))
    monkeypatch.setattr("app.jobs.reconcile_game_expiry.JobRunRecorder", lambda: recorder)
    monkeypatch.setattr(
        "app.jobs.reconcile_game_expiry.reconcile_expired_games",
        lambda **_: {"scanned_count": 1, "reconciled_count": 1, "skipped_count": 0},
    )

    with caplog.at_level("WARNING", logger="app.jobs.reconcile_game_expiry"):
        assert expiry_job_main([]) == 0

    assert recorder.succeeded
    assert any(
        getattr(record, "monitoring_stage", None) == "success"
        for record in caplog.records
    )


def test_cli_failure_finalization_failure_preserves_original_failure(monkeypatch, caplog):
    recorder = FakeJobRunRecorder(failure_error=TimeoutError("timeout"))

    def fail(**_: Any):
        raise RuntimeError("original database failure")

    monkeypatch.setattr("app.jobs.reconcile_game_expiry.JobRunRecorder", lambda: recorder)
    monkeypatch.setattr("app.jobs.reconcile_game_expiry.reconcile_expired_games", fail)

    with caplog.at_level("WARNING", logger="app.jobs.reconcile_game_expiry"):
        assert expiry_job_main([]) == 1

    assert recorder.failed
    assert any(
        getattr(record, "monitoring_stage", None) == "failure"
        for record in caplog.records
    )


def test_job_run_error_messages_are_sanitized_and_bounded():
    raw = "database failed password=super-secret token=abc123 " + ("x" * 700)

    sanitized = sanitize_error_message(raw)

    assert "super-secret" not in sanitized
    assert "abc123" not in sanitized
    assert "password=[REDACTED]" in sanitized
    assert "token=[REDACTED]" in sanitized
    assert len(sanitized) <= 500


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


def test_job_runs_migration_defines_persistent_job_run_table():
    repo_root = Path(__file__).resolve().parents[2]
    migration = (repo_root / "backend/migrations/job_runs.sql").read_text(
        encoding="utf-8",
    )

    assert "create table if not exists public.job_runs" in migration.lower()
    assert "status in ('running', 'succeeded', 'failed')" in migration
    assert "alter table public.job_runs enable row level security" in migration.lower()
    assert "grant select, insert, update on public.job_runs to service_role" in migration.lower()
    assert "idx_job_runs_job_name_started_at" in migration
