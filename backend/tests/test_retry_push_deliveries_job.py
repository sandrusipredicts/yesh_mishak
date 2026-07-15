from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.jobs.retry_push_deliveries import main, JOB_NAME


class FakeJobRun:
    def __init__(self) -> None:
        self.id = "run-1"
        self.job_name = JOB_NAME
        self.started_at = None
        self.start_monotonic = 0.0


class FakeRecorder:
    def __init__(self) -> None:
        self.started = False
        self.succeeded = False
        self.failed = False
        self.result: dict[str, Any] | None = None
        self.exc: BaseException | None = None

    def start(self, *, job_name: str, metadata: dict[str, Any] | None = None) -> FakeJobRun:
        self.started = True
        return FakeJobRun()

    def mark_succeeded(self, job_run: Any, result: dict[str, Any]) -> None:
        self.succeeded = True
        self.result = result

    def mark_failed(self, job_run: Any, exc: BaseException) -> None:
        self.failed = True
        self.exc = exc


class TestRetryJob:
    def test_job_returns_zero_on_success(self):
        recorder = FakeRecorder()
        with patch("app.jobs.retry_push_deliveries.JobRunRecorder", return_value=recorder), \
             patch("app.jobs.retry_push_deliveries.process_retry_batch", return_value={
                 "claimed": 0, "delivered": 0, "failed_retryable": 0,
                 "failed_permanent": 0, "abandoned": 0,
             }), \
             patch("app.db.supabase.get_supabase_service_role_client", return_value=MagicMock()):
            code = main([])
        assert code == 0
        assert recorder.succeeded

    def test_job_returns_one_on_exception(self):
        recorder = FakeRecorder()
        with patch("app.jobs.retry_push_deliveries.JobRunRecorder", return_value=recorder), \
             patch("app.jobs.retry_push_deliveries.process_retry_batch", side_effect=RuntimeError("boom")), \
             patch("app.db.supabase.get_supabase_service_role_client", return_value=MagicMock()):
            code = main([])
        assert code == 1
        assert recorder.failed

    def test_job_records_job_run_via_recorder(self):
        recorder = FakeRecorder()
        with patch("app.jobs.retry_push_deliveries.JobRunRecorder", return_value=recorder), \
             patch("app.jobs.retry_push_deliveries.process_retry_batch", return_value={
                 "claimed": 2, "delivered": 1, "failed_retryable": 1,
                 "failed_permanent": 0, "abandoned": 0,
             }), \
             patch("app.db.supabase.get_supabase_service_role_client", return_value=MagicMock()):
            code = main(["--max-batches", "1"])
        assert code == 0
        assert recorder.started
        assert recorder.succeeded
        assert recorder.result is not None
        assert recorder.result["reconciled_count"] == 1
