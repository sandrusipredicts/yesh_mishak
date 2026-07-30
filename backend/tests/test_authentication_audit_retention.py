from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Any

import pytest

from app.jobs import cleanup_authentication_audit_events as cleanup_job
from app.services.authentication_audit_retention import (
    AUTHENTICATION_AUDIT_RETENTION_DAYS,
    AuthenticationAuditCleanupRpcError,
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_BATCHES,
    MAX_BATCH_SIZE,
    MAX_MAX_BATCHES,
    SecurityEvidenceCleanupError,
    UnexpectedAuthenticationAuditCleanupResponse,
    cleanup_authentication_audit_events,
    cleanup_security_evidence_events,
)
from app.services.job_runs import JobRun, JobRunRecorder


NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


@dataclass
class FakeResponse:
    data: Any


class FakeRpcClient:
    def __init__(
        self,
        responses: list[Any] | None = None,
        *,
        errors: list[Exception | None] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.errors = list(errors or [])
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> "FakeRpcClient":
        self.calls.append((name, dict(params)))
        return self

    def execute(self) -> FakeResponse:
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        value = self.responses.pop(0) if self.responses else 0
        return FakeResponse(value)


class FakeRecorder:
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
            id="retention-job-run",
            job_name=cleanup_job.JOB_NAME,
            started_at=NOW,
            start_monotonic=time.perf_counter(),
        )

    def start(
        self,
        *,
        job_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> JobRun:
        self.started.append(
            {"job_name": job_name, "metadata": metadata or {}},
        )
        if self.start_error is not None:
            raise self.start_error
        return self.job_run

    def mark_succeeded(
        self,
        job_run: JobRun,
        result: dict[str, Any],
    ) -> None:
        self.succeeded.append((job_run, result))
        if self.success_error is not None:
            raise self.success_error

    def mark_failed(self, job_run: JobRun, exc: BaseException) -> None:
        self.failed.append((job_run, exc))
        if self.failure_error is not None:
            raise self.failure_error


def cleanup_result(
    *,
    processed_count: int = 0,
    batch_count: int = 1,
    reached_max_batches: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int = DEFAULT_MAX_BATCHES,
) -> dict[str, int | bool]:
    return {
        "processed_count": processed_count,
        "deleted_count": processed_count,
        "batch_count": batch_count,
        "reached_max_batches": reached_max_batches,
        "retention_days": AUTHENTICATION_AUDIT_RETENTION_DAYS,
        "batch_size": batch_size,
        "max_batches": max_batches,
    }


def security_cleanup_result(
    *,
    authentication_deleted: int = 0,
    attribution_deleted: int = 0,
    investigation_deleted: int = 0,
    batch_count: int = 3,
    reached_max_batches: bool = False,
) -> dict[str, int | bool]:
    processed_count = (
        authentication_deleted
        + attribution_deleted
        + investigation_deleted
    )
    target_batch_count = batch_count // 3
    return {
        "processed_count": processed_count,
        "deleted_count": processed_count,
        "batch_count": batch_count,
        "reached_max_batches": reached_max_batches,
        "retention_days": AUTHENTICATION_AUDIT_RETENTION_DAYS,
        "batch_size": DEFAULT_BATCH_SIZE,
        "max_batches": DEFAULT_MAX_BATCHES,
        "target_count": 3,
        "failed_target_count": 0,
        "authentication_audit_deleted_count": authentication_deleted,
        "authentication_audit_batch_count": target_batch_count,
        "security_attribution_deleted_count": attribution_deleted,
        "security_attribution_batch_count": target_batch_count,
        "investigation_access_deleted_count": investigation_deleted,
        "investigation_access_batch_count": target_batch_count,
    }


def test_cutoff_is_exactly_180_days_and_zero_stops_immediately() -> None:
    client = FakeRpcClient([0])

    result = cleanup_authentication_audit_events(
        supabase=client,
        now=NOW,
    )

    assert result == cleanup_result()
    assert client.calls == [
        (
            "cleanup_authentication_audit_events",
            {
                "p_cutoff": "2026-01-31T12:00:00+00:00",
                "p_batch_limit": DEFAULT_BATCH_SIZE,
            },
        )
    ]


def test_multiple_batches_continue_until_an_explicit_zero() -> None:
    client = FakeRpcClient([1_000, [1_000], 25, [0]])

    result = cleanup_authentication_audit_events(
        supabase=client,
        now=NOW,
    )

    assert result == cleanup_result(
        processed_count=2_025,
        batch_count=4,
    )
    assert len(client.calls) == 4
    assert len({call[1]["p_cutoff"] for call in client.calls}) == 1


def test_max_batch_guard_stops_runaway_work() -> None:
    client = FakeRpcClient([2, 2, 0])

    result = cleanup_authentication_audit_events(
        supabase=client,
        now=NOW,
        batch_size=2,
        max_batches=2,
    )

    assert result == cleanup_result(
        processed_count=4,
        batch_count=2,
        reached_max_batches=True,
        batch_size=2,
        max_batches=2,
    )
    assert len(client.calls) == 2


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"batch_size": 0}, "batch_size must be between 1 and 1000"),
        ({"batch_size": MAX_BATCH_SIZE + 1}, "batch_size must be between"),
        ({"batch_size": True}, "batch_size must be an integer"),
        ({"max_batches": 0}, "max_batches must be between 1 and 100"),
        ({"max_batches": MAX_MAX_BATCHES + 1}, "max_batches must be between"),
        ({"max_batches": False}, "max_batches must be an integer"),
    ],
)
def test_configured_bounds_are_enforced(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        cleanup_authentication_audit_events(
            supabase=FakeRpcClient(),
            now=NOW,
            **kwargs,
        )


def test_naive_reference_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        cleanup_authentication_audit_events(
            supabase=FakeRpcClient(),
            now=datetime(2026, 7, 30, 12, 0),
        )


@pytest.mark.parametrize(
    "malformed_response",
    [[], [1, 2], None, {}, "1", 1.0, True, -1, 6],
)
def test_malformed_rpc_response_shapes_fail_safely(
    malformed_response: Any,
) -> None:
    with pytest.raises(UnexpectedAuthenticationAuditCleanupResponse):
        cleanup_authentication_audit_events(
            supabase=FakeRpcClient([malformed_response]),
            now=NOW,
            batch_size=5,
        )


def test_rpc_failure_can_be_retried_without_changing_the_cutoff() -> None:
    secret = RuntimeError("database unavailable password=must-not-escape")
    first_attempt = FakeRpcClient(errors=[secret])

    with pytest.raises(
        AuthenticationAuditCleanupRpcError,
        match="cleanup_rpc_failure",
    ) as exc_info:
        cleanup_authentication_audit_events(
            supabase=first_attempt,
            now=NOW,
            batch_size=2,
            max_batches=3,
        )
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None
    assert "must-not-escape" not in repr(exc_info.value)

    retry = FakeRpcClient([2, 0])
    result = cleanup_authentication_audit_events(
        supabase=retry,
        now=NOW,
        batch_size=2,
        max_batches=3,
    )

    assert result["deleted_count"] == 2
    assert first_attempt.calls[0][1] == retry.calls[0][1]


def test_security_cleanup_processes_all_targets_with_one_fixed_cutoff() -> None:
    client = FakeRpcClient([2, 0, 3, 0, 4, 0])

    result = cleanup_security_evidence_events(
        supabase=client,
        now=NOW,
    )

    assert result == security_cleanup_result(
        authentication_deleted=2,
        attribution_deleted=3,
        investigation_deleted=4,
        batch_count=6,
    )
    assert [call[0] for call in client.calls] == [
        "cleanup_authentication_audit_events",
        "cleanup_authentication_audit_events",
        "cleanup_security_request_attribution_events",
        "cleanup_security_request_attribution_events",
        "cleanup_security_investigation_access_events",
        "cleanup_security_investigation_access_events",
    ]
    assert len({call[1]["p_cutoff"] for call in client.calls}) == 1


def test_security_cleanup_attempts_other_targets_after_one_rpc_failure() -> None:
    client = FakeRpcClient(
        [1, 0, 2, 0],
        errors=[None, None, RuntimeError("database secret"), None, None],
    )

    with pytest.raises(
        SecurityEvidenceCleanupError,
        match="cleanup_rpc_failure",
    ) as exc_info:
        cleanup_security_evidence_events(
            supabase=client,
            now=NOW,
        )

    assert [call[0] for call in client.calls] == [
        "cleanup_authentication_audit_events",
        "cleanup_authentication_audit_events",
        "cleanup_security_request_attribution_events",
        "cleanup_security_investigation_access_events",
        "cleanup_security_investigation_access_events",
    ]
    assert exc_info.value.partial_result == {
        "processed_count": 3,
        "deleted_count": 3,
        "batch_count": 4,
        "reached_max_batches": False,
        "retention_days": AUTHENTICATION_AUDIT_RETENTION_DAYS,
        "batch_size": DEFAULT_BATCH_SIZE,
        "max_batches": DEFAULT_MAX_BATCHES,
        "target_count": 3,
        "failed_target_count": 1,
        "authentication_audit_deleted_count": 1,
        "authentication_audit_batch_count": 2,
        "investigation_access_deleted_count": 2,
        "investigation_access_batch_count": 2,
    }
    assert "secret" not in repr(exc_info.value)


def test_job_records_bounded_success_evidence(monkeypatch, capsys) -> None:
    recorder = FakeRecorder()
    result = security_cleanup_result(
        authentication_deleted=2,
        attribution_deleted=3,
        investigation_deleted=2,
        batch_count=6,
    )
    monkeypatch.setattr(cleanup_job, "JobRunRecorder", lambda: recorder)
    monkeypatch.setattr(
        cleanup_job,
        "cleanup_security_evidence_events",
        lambda **_kwargs: result,
    )

    assert cleanup_job.main([]) == 0

    assert recorder.started == [
        {
            "job_name": cleanup_job.JOB_NAME,
            "metadata": {
                "retention_days": AUTHENTICATION_AUDIT_RETENTION_DAYS,
                "batch_size": DEFAULT_BATCH_SIZE,
                "max_batches": DEFAULT_MAX_BATCHES,
                "entry_point": cleanup_job.ENTRY_POINT,
                "cleanup_target_count": 3,
            },
        }
    ]
    assert recorder.succeeded == [(recorder.job_run, result)]
    assert recorder.failed == []
    assert '"processed_count": 7' in capsys.readouterr().out


def test_job_records_sanitized_failure_and_returns_nonzero(
    monkeypatch,
    caplog,
    capsys,
) -> None:
    recorder = FakeRecorder()
    sentinels = (
        "password=personal-secret",
        "email=person@example.invalid",
        "user_id=00000000-0000-4000-8000-000000001031",
        "correlation_id=private-correlation",
        "event_id=00000000-0000-4000-8000-000000001032",
        "Authorization=Bearer private-token",
    )
    monkeypatch.setattr(cleanup_job, "JobRunRecorder", lambda: recorder)
    monkeypatch.setattr(
        cleanup_job,
        "cleanup_security_evidence_events",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError(" ".join(sentinels)),
        ),
    )

    with caplog.at_level(logging.WARNING, logger=cleanup_job.__name__):
        assert cleanup_job.main([]) == 1

    assert len(recorder.failed) == 1
    safe_failure = recorder.failed[0][1]
    assert isinstance(
        safe_failure,
        cleanup_job.AuthenticationAuditCleanupJobFailure,
    )
    assert str(safe_failure) == "cleanup_rpc_failure"
    assert safe_failure.__context__ is None
    assert safe_failure.__cause__ is None
    serialized = caplog.text + capsys.readouterr().out + repr(recorder.failed)
    for sentinel in sentinels:
        assert sentinel not in serialized
    assert recorder.succeeded == []


def test_unexpected_response_uses_a_bounded_failure_category(
    monkeypatch,
    caplog,
) -> None:
    recorder = FakeRecorder()
    monkeypatch.setattr(cleanup_job, "JobRunRecorder", lambda: recorder)
    monkeypatch.setattr(
        cleanup_job,
        "cleanup_security_evidence_events",
        lambda **_kwargs: (_ for _ in ()).throw(
            UnexpectedAuthenticationAuditCleanupResponse(
                "malformed response private-value",
            ),
        ),
    )

    with caplog.at_level(logging.WARNING, logger=cleanup_job.__name__):
        assert cleanup_job.main([]) == 1

    assert str(recorder.failed[0][1]) == "unexpected_response"
    assert "private-value" not in caplog.text


@pytest.mark.parametrize(
    "recorder",
    [
        FakeRecorder(start_error=RuntimeError("monitoring secret")),
        FakeRecorder(success_error=RuntimeError("monitoring secret")),
    ],
    ids=["start", "success-finalization"],
)
def test_monitoring_failure_does_not_crash_successful_cleanup(
    monkeypatch,
    recorder: FakeRecorder,
) -> None:
    monkeypatch.setattr(cleanup_job, "JobRunRecorder", lambda: recorder)
    monkeypatch.setattr(
        cleanup_job,
        "cleanup_security_evidence_events",
        lambda **_kwargs: security_cleanup_result(),
    )

    assert cleanup_job.main([]) == 0


def test_failure_monitoring_and_logger_failures_do_not_crash_job(
    monkeypatch,
) -> None:
    recorder = FakeRecorder(
        failure_error=RuntimeError("monitoring password=secret"),
    )
    monkeypatch.setattr(cleanup_job, "JobRunRecorder", lambda: recorder)
    monkeypatch.setattr(
        cleanup_job,
        "cleanup_security_evidence_events",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("database password=secret"),
        ),
    )
    monkeypatch.setattr(
        cleanup_job.logger,
        "warning",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("logger failed"),
        ),
    )

    assert cleanup_job.main([]) == 1


def test_capacity_warning_logger_failure_does_not_change_success(
    monkeypatch,
) -> None:
    recorder = FakeRecorder()
    monkeypatch.setattr(cleanup_job, "JobRunRecorder", lambda: recorder)
    monkeypatch.setattr(
        cleanup_job,
        "cleanup_security_evidence_events",
        lambda **_kwargs: security_cleanup_result(
            authentication_deleted=50_000,
            batch_count=52,
            reached_max_batches=True,
        ),
    )
    monkeypatch.setattr(
        cleanup_job.logger,
        "warning",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("logger failed"),
        ),
    )

    assert cleanup_job.main([]) == 0
    assert recorder.succeeded[0][1]["reached_max_batches"] is True


def test_cli_rejects_out_of_bounds_work_controls() -> None:
    with pytest.raises(SystemExit):
        cleanup_job.main(["--batch-size", "0"])
    with pytest.raises(SystemExit):
        cleanup_job.main(["--batch-size", "1001"])
    with pytest.raises(SystemExit):
        cleanup_job.main(["--max-batches", "0"])
    with pytest.raises(SystemExit):
        cleanup_job.main(["--max-batches", "101"])


class FakeJobRunUpdateClient:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    def table(self, name: str) -> "FakeJobRunUpdateClient":
        assert name == "job_runs"
        return self

    def update(self, payload: dict[str, Any]) -> "FakeJobRunUpdateClient":
        self.payload = payload
        return self

    def eq(self, column: str, value: str) -> "FakeJobRunUpdateClient":
        assert (column, value) == ("id", "retention-job-run")
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse([])


def test_job_run_recorder_persists_retention_processed_count() -> None:
    client = FakeJobRunUpdateClient()
    recorder = JobRunRecorder(supabase=client)
    job_run = JobRun(
        id="retention-job-run",
        job_name=cleanup_job.JOB_NAME,
        started_at=NOW,
        start_monotonic=time.perf_counter(),
    )

    recorder.mark_succeeded(
        job_run,
        cleanup_result(processed_count=321, batch_count=4),
    )

    assert client.payload is not None
    assert client.payload["processed_count"] == 321
    assert client.payload["reconciled_count"] is None
    assert client.payload["batch_count"] == 4
    assert client.payload["reached_max_batches"] is False
