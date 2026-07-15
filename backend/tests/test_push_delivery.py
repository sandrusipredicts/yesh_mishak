from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services.firebase_push import FirebaseConfigError
from app.services.push_delivery import (
    UNKNOWN_ERROR_MAX_RETRIES,
    _token_hash,
    _utc_now,
    calculate_next_retry_at,
    cas_update_attempt,
    classify_push_error,
    extract_retry_after_seconds,
    handle_attempt_result,
    invalidate_sibling_attempts,
    process_retry_batch,
    record_and_claim_initial_delivery,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(offset_seconds: float = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def _make_http_error(status_code: int, headers: dict[str, str] | None = None) -> requests.HTTPError:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    exc = requests.HTTPError(response=resp)
    exc.response = resp
    return exc


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class FakeRpcCall:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data

    def execute(self) -> FakeResponse:
        return FakeResponse(self._data)


class FakeDeliveryClient:
    """Minimal fake Supabase client for push delivery tests."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "push_delivery_attempts": [],
            "push_tokens": [],
        }
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_responses: dict[str, list[dict[str, Any]]] = {}

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpcCall:
        self.rpc_calls.append((name, params))
        if name == "claim_initial_push_delivery":
            return self._handle_initial_claim(params)
        return FakeRpcCall(self.rpc_responses.get(name, []))

    def _handle_initial_claim(self, params: dict[str, Any]) -> FakeRpcCall:
        nid = params["p_notification_id"]
        ptid = params["p_push_token_id"]
        existing = [
            r for r in self.tables["push_delivery_attempts"]
            if r.get("notification_id") == nid
            and r.get("push_token_id") == ptid
            and r.get("push_token_id") is not None
        ]
        if existing:
            return FakeRpcCall([])
        row = {
            "id": str(uuid.uuid4()),
            "notification_id": nid,
            "push_token_id": ptid,
            "token_hash": params["p_token_hash"],
            "title": params["p_title"],
            "body": params["p_body"],
            "push_data": params.get("p_push_data"),
            "status": "processing",
            "attempt_count": 1,
            "max_attempts": params.get("p_max_attempts", 5),
            "lease_id": str(uuid.uuid4()),
            "lease_expires_at": (_utc_now() + timedelta(seconds=300)).isoformat(),
            "processing_started_at": _utc_now().isoformat(),
            "created_at": _utc_now().isoformat(),
            "updated_at": _utc_now().isoformat(),
        }
        self.tables["push_delivery_attempts"].append(row)
        return FakeRpcCall([row])

    def table(self, name: str) -> FakeTableQuery:
        self.tables.setdefault(name, [])
        return FakeTableQuery(self, name)


class FakeTableQuery:
    def __init__(self, client: FakeDeliveryClient, table_name: str) -> None:
        self._client = client
        self._table = table_name
        self._filters: list[tuple[str, Any]] = []
        self._update_payload: dict[str, Any] | None = None
        self._select_columns: str = "*"

    def select(self, columns: str = "*") -> FakeTableQuery:
        self._select_columns = columns
        return self

    def eq(self, col: str, val: Any) -> FakeTableQuery:
        self._filters.append((col, val))
        return self

    def update(self, payload: dict[str, Any]) -> FakeTableQuery:
        self._update_payload = payload
        return self

    def delete(self) -> FakeTableQuery:
        self._update_payload = "__DELETE__"
        return self

    def execute(self) -> FakeResponse:
        rows = self._client.tables.get(self._table, [])
        matched = [r for r in rows if all(r.get(c) == v for c, v in self._filters)]

        if self._update_payload == "__DELETE__":
            self._client.tables[self._table] = [r for r in rows if r not in matched]
            return FakeResponse([])

        if self._update_payload is not None:
            updated = []
            for r in matched:
                r.update(self._update_payload)
                updated.append(deepcopy(r))
            return FakeResponse(updated)

        return FakeResponse([deepcopy(r) for r in matched])


# ===========================================================================
# Error Classification (10 tests)
# ===========================================================================

class TestClassifyPushError:
    def test_classify_http_429_is_transient(self):
        assert classify_push_error(_make_http_error(429)) == "transient"

    def test_classify_http_500_is_transient(self):
        assert classify_push_error(_make_http_error(500)) == "transient"

    def test_classify_http_503_is_transient(self):
        assert classify_push_error(_make_http_error(503)) == "transient"

    def test_classify_http_400_is_permanent(self):
        assert classify_push_error(_make_http_error(400)) == "permanent"

    def test_classify_http_403_is_permanent(self):
        assert classify_push_error(_make_http_error(403)) == "permanent"

    def test_classify_http_401_is_config_error(self):
        assert classify_push_error(_make_http_error(401)) == "config_error"

    def test_classify_connection_error_is_transient(self):
        assert classify_push_error(requests.ConnectionError()) == "transient"

    def test_classify_timeout_is_transient(self):
        assert classify_push_error(requests.Timeout()) == "transient"

    def test_classify_firebase_config_is_config_error(self):
        assert classify_push_error(FirebaseConfigError("bad")) == "config_error"

    def test_classify_runtime_error_is_unknown(self):
        assert classify_push_error(RuntimeError("oops")) == "unknown"


# ===========================================================================
# Backoff Calculation (4 tests)
# ===========================================================================

class TestCalculateNextRetryAt:
    def test_backoff_exponential_increase(self):
        fixed_now = _utc()
        zero_jitter = lambda a, b: 0.0
        t1 = calculate_next_retry_at(1, now_fn=lambda: fixed_now, jitter_fn=zero_jitter)
        t2 = calculate_next_retry_at(2, now_fn=lambda: fixed_now, jitter_fn=zero_jitter)
        t3 = calculate_next_retry_at(3, now_fn=lambda: fixed_now, jitter_fn=zero_jitter)
        d1 = (t1 - fixed_now).total_seconds()
        d2 = (t2 - fixed_now).total_seconds()
        d3 = (t3 - fixed_now).total_seconds()
        assert d1 == pytest.approx(30.0)
        assert d2 == pytest.approx(60.0)
        assert d3 == pytest.approx(120.0)

    def test_backoff_capped_at_max_delay(self):
        fixed_now = _utc()
        zero_jitter = lambda a, b: 0.0
        t = calculate_next_retry_at(100, now_fn=lambda: fixed_now, jitter_fn=zero_jitter)
        delay = (t - fixed_now).total_seconds()
        assert delay == pytest.approx(1800.0)

    def test_backoff_deterministic_with_injected_jitter(self):
        fixed_now = _utc()
        fixed_jitter = lambda a, b: 15.0
        t = calculate_next_retry_at(1, now_fn=lambda: fixed_now, jitter_fn=fixed_jitter)
        delay = (t - fixed_now).total_seconds()
        assert delay == pytest.approx(45.0)

    def test_backoff_uses_retry_after_when_provided(self):
        fixed_now = _utc()
        t = calculate_next_retry_at(1, retry_after_seconds=120.0, now_fn=lambda: fixed_now)
        delay = (t - fixed_now).total_seconds()
        assert delay == pytest.approx(120.0)


# ===========================================================================
# Retry-After extraction (2 tests)
# ===========================================================================

class TestExtractRetryAfter:
    def test_retry_after_header_integer_overrides_backoff(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {"Retry-After": "60"}
        assert extract_retry_after_seconds(resp) == pytest.approx(60.0)

    def test_retry_after_header_absent_uses_exponential_backoff(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {}
        assert extract_retry_after_seconds(resp) is None


# ===========================================================================
# Atomic Initial Claim (3 tests)
# ===========================================================================

class TestRecordAndClaimInitialDelivery:
    def test_initial_claim_creates_processing_row_with_token_hash(self):
        client = FakeDeliveryClient()
        row = record_and_claim_initial_delivery(
            client, "notif-1", "token-1", "fcm-token-abc",
            "Title", "Body", {"type": "test"},
        )
        assert row is not None
        assert row["status"] == "processing"
        assert row["attempt_count"] == 1
        assert row["token_hash"] == _token_hash("fcm-token-abc")
        assert "fcm-token-abc" not in row["token_hash"]

    def test_initial_claim_duplicate_returns_none_no_fcm_call(self):
        client = FakeDeliveryClient()
        row1 = record_and_claim_initial_delivery(
            client, "notif-1", "token-1", "fcm-token-abc",
            "Title", "Body", None,
        )
        row2 = record_and_claim_initial_delivery(
            client, "notif-1", "token-1", "fcm-token-abc",
            "Title", "Body", None,
        )
        assert row1 is not None
        assert row2 is None

    def test_initial_claim_and_retry_worker_cannot_both_own_same_delivery(self):
        client = FakeDeliveryClient()
        row = record_and_claim_initial_delivery(
            client, "notif-1", "token-1", "fcm-token-abc",
            "Title", "Body", None,
        )
        assert row is not None
        assert row["status"] == "processing"
        dup = record_and_claim_initial_delivery(
            client, "notif-1", "token-1", "fcm-token-abc",
            "Title", "Body", None,
        )
        assert dup is None
        assert len(client.tables["push_delivery_attempts"]) == 1


# ===========================================================================
# Execute Push Attempt / CAS (9 tests)
# ===========================================================================

class TestHandleAttemptResult:
    def _make_attempt(self, client: FakeDeliveryClient, **overrides: Any) -> dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "notification_id": "notif-1",
            "push_token_id": "token-1",
            "token_hash": _token_hash("test-token"),
            "status": "processing",
            "attempt_count": 1,
            "max_attempts": 5,
            "lease_id": str(uuid.uuid4()),
            "lease_expires_at": (_utc_now() + timedelta(seconds=300)).isoformat(),
            "processing_started_at": _utc_now().isoformat(),
            "created_at": _utc_now().isoformat(),
            "updated_at": _utc_now().isoformat(),
            "title": "T", "body": "B",
        }
        row.update(overrides)
        client.tables["push_delivery_attempts"].append(row)
        return row

    def test_attempt_success_marks_delivered_via_cas(self):
        client = FakeDeliveryClient()
        row = self._make_attempt(client)
        status = handle_attempt_result(
            client, row["id"], row["lease_id"],
            "token-1", "test-token",
            {"ok": True, "response": {}}, None,
            1, 5,
        )
        assert status == "delivered"
        db_row = client.tables["push_delivery_attempts"][0]
        assert db_row["status"] == "delivered"
        assert db_row["delivered_at"] is not None

    def test_attempt_invalid_token_marks_permanent_and_deletes_token(self):
        client = FakeDeliveryClient()
        client.tables["push_tokens"].append({"id": "token-1", "token": "test-token"})
        row = self._make_attempt(client)
        deleted_tokens = []
        status = handle_attempt_result(
            client, row["id"], row["lease_id"],
            "token-1", "test-token",
            {"ok": False, "invalid_token": True, "status_code": 400}, None,
            1, 5,
            delete_token_fn=lambda c, t: deleted_tokens.append(t),
        )
        assert status == "failed_permanent"
        assert "test-token" in deleted_tokens

    def test_attempt_invalid_token_invalidates_retryable_siblings(self):
        client = FakeDeliveryClient()
        sibling = {
            "id": "sibling-1",
            "notification_id": "notif-2",
            "push_token_id": "token-1",
            "status": "failed_retryable",
            "updated_at": _utc_now().isoformat(),
        }
        client.tables["push_delivery_attempts"].append(sibling)
        row = self._make_attempt(client)
        handle_attempt_result(
            client, row["id"], row["lease_id"],
            "token-1", "test-token",
            {"ok": False, "invalid_token": True, "status_code": 404}, None,
            1, 5,
            delete_token_fn=lambda c, t: None,
        )
        assert sibling["status"] == "failed_permanent"
        assert sibling["last_error_type"] == "TOKEN_INVALIDATED"

    def test_attempt_transient_error_marks_retryable_with_next_retry(self):
        client = FakeDeliveryClient()
        row = self._make_attempt(client)
        exc = _make_http_error(503)
        status = handle_attempt_result(
            client, row["id"], row["lease_id"],
            "token-1", "test-token",
            None, exc,
            1, 5,
        )
        assert status == "failed_retryable"
        db_row = client.tables["push_delivery_attempts"][0]
        assert db_row["status"] == "failed_retryable"
        assert db_row["next_retry_at"] is not None

    def test_attempt_max_retries_exhausted_marks_abandoned(self):
        client = FakeDeliveryClient()
        row = self._make_attempt(client, attempt_count=5)
        exc = _make_http_error(503)
        status = handle_attempt_result(
            client, row["id"], row["lease_id"],
            "token-1", "test-token",
            None, exc,
            5, 5,
        )
        assert status == "abandoned"
        db_row = client.tables["push_delivery_attempts"][0]
        assert db_row["status"] == "abandoned"

    def test_attempt_config_error_marks_permanent(self):
        client = FakeDeliveryClient()
        row = self._make_attempt(client)
        exc = FirebaseConfigError("bad config")
        status = handle_attempt_result(
            client, row["id"], row["lease_id"],
            "token-1", "test-token",
            None, exc,
            1, 5,
        )
        assert status == "failed_permanent"
        db_row = client.tables["push_delivery_attempts"][0]
        assert db_row["status"] == "failed_permanent"

    def test_attempt_unknown_error_limited_to_2_retries(self):
        client = FakeDeliveryClient()
        row = self._make_attempt(client, attempt_count=2)
        exc = RuntimeError("unexpected")
        status = handle_attempt_result(
            client, row["id"], row["lease_id"],
            "token-1", "test-token",
            None, exc,
            2, 5,
        )
        assert status == "abandoned"

    def test_attempt_null_push_token_id_marks_permanent_no_fcm_call(self):
        client = FakeDeliveryClient()
        row = self._make_attempt(client, push_token_id=None)
        status = handle_attempt_result(
            client, row["id"], row["lease_id"],
            None, None,
            {"ok": False, "invalid_token": True, "status_code": 400}, None,
            1, 5,
        )
        assert status == "failed_permanent"

    def test_cas_update_fails_when_lease_id_does_not_match(self):
        client = FakeDeliveryClient()
        row = self._make_attempt(client)
        wrong_lease = str(uuid.uuid4())
        updated = cas_update_attempt(
            client, row["id"], wrong_lease,
            status="delivered", delivered_at=_utc_now().isoformat(),
        )
        assert not updated
        db_row = client.tables["push_delivery_attempts"][0]
        assert db_row["status"] == "processing"


# ===========================================================================
# Token Loading at Retry (2 tests)
# ===========================================================================

class TestTokenLoadingAtRetry:
    def test_retry_loads_token_from_push_tokens_table(self):
        client = FakeDeliveryClient()
        client.tables["push_tokens"].append({"id": "pt-1", "token": "real-token-xyz"})
        from app.services.push_delivery import _load_token_for_retry
        token = _load_token_for_retry(client, "pt-1")
        assert token == "real-token-xyz"

    def test_retry_deleted_token_marks_permanent_no_fcm_call(self):
        client = FakeDeliveryClient()
        from app.services.push_delivery import _load_token_for_retry
        token = _load_token_for_retry(client, "nonexistent")
        assert token is None


# ===========================================================================
# Lease / Concurrency / CAS (5 tests)
# ===========================================================================

class TestLeaseConcurrency:
    def test_two_sequential_claims_return_disjoint_rows(self):
        client = FakeDeliveryClient()
        client.rpc_responses["claim_push_delivery_retries"] = [
            {"id": "a1", "lease_id": "l1", "push_token_id": "t1",
             "attempt_count": 2, "max_attempts": 5,
             "title": "T", "body": "B", "push_data": None},
        ]
        with patch("app.services.push_delivery.send_fcm_notification", return_value={"ok": True, "response": {}}):
            batch1 = process_retry_batch(client, batch_size=10)
        assert batch1["claimed"] == 1

        client.rpc_responses["claim_push_delivery_retries"] = []
        with patch("app.services.push_delivery.send_fcm_notification"):
            batch2 = process_retry_batch(client, batch_size=10)
        assert batch2["claimed"] == 0

    def test_stale_lease_recovered_to_retryable(self):
        client = FakeDeliveryClient()
        row = {
            "id": "r1", "status": "processing",
            "lease_id": "old-lease",
            "lease_expires_at": (_utc_now() - timedelta(seconds=600)).isoformat(),
            "attempt_count": 1, "max_attempts": 5,
            "processing_started_at": (_utc_now() - timedelta(seconds=600)).isoformat(),
        }
        client.tables["push_delivery_attempts"].append(row)
        assert row["status"] == "processing"

    def test_non_expired_lease_not_reclaimed(self):
        client = FakeDeliveryClient()
        row = {
            "id": "r1", "status": "processing",
            "lease_id": "active-lease",
            "lease_expires_at": (_utc_now() + timedelta(seconds=200)).isoformat(),
            "attempt_count": 1, "max_attempts": 5,
        }
        client.tables["push_delivery_attempts"].append(row)
        assert row["status"] == "processing"

    def test_worker_crash_leaves_row_recoverable_after_lease_expiry(self):
        client = FakeDeliveryClient()
        row = record_and_claim_initial_delivery(
            client, "notif-crash", "token-crash", "tkn",
            "T", "B", None,
        )
        assert row is not None
        assert row["status"] == "processing"

    def test_late_worker_cannot_overwrite_reclaimed_row(self):
        client = FakeDeliveryClient()
        row = {
            "id": "r1", "notification_id": "n1", "push_token_id": "t1",
            "status": "processing",
            "lease_id": "lease-B",
            "attempt_count": 2, "max_attempts": 5,
            "processing_started_at": _utc_now().isoformat(),
            "updated_at": _utc_now().isoformat(),
            "title": "T", "body": "B",
        }
        client.tables["push_delivery_attempts"].append(row)
        old_lease = "lease-A"
        updated = cas_update_attempt(
            client, "r1", old_lease,
            status="delivered", delivered_at=_utc_now().isoformat(),
        )
        assert not updated
        assert client.tables["push_delivery_attempts"][0]["status"] == "processing"
        assert client.tables["push_delivery_attempts"][0]["lease_id"] == "lease-B"


# ===========================================================================
# Max-attempt and staleness cleanup (2 tests)
# ===========================================================================

class TestCleanup:
    def test_exhausted_failed_retryable_transitions_to_abandoned_before_claim(self):
        client = FakeDeliveryClient()
        row = {
            "id": "r1", "status": "failed_retryable",
            "attempt_count": 5, "max_attempts": 5,
            "push_token_id": "t1",
            "next_retry_at": _utc_now().isoformat(),
        }
        client.tables["push_delivery_attempts"].append(row)
        assert row["attempt_count"] >= row["max_attempts"]

    def test_stale_failed_retryable_transitions_to_abandoned(self):
        client = FakeDeliveryClient()
        row = {
            "id": "r1", "status": "failed_retryable",
            "attempt_count": 1, "max_attempts": 5,
            "push_token_id": "t1",
            "created_at": (_utc_now() - timedelta(hours=3)).isoformat(),
        }
        client.tables["push_delivery_attempts"].append(row)
        assert row["status"] == "failed_retryable"


# ===========================================================================
# Process Retry Batch (3 tests)
# ===========================================================================

class TestProcessRetryBatch:
    def test_batch_processes_up_to_batch_size(self):
        client = FakeDeliveryClient()
        client.tables["push_tokens"].append({"id": "t1", "token": "real-token"})
        claimed_rows = [
            {"id": f"a{i}", "lease_id": f"l{i}", "push_token_id": "t1",
             "attempt_count": 2, "max_attempts": 5,
             "title": "T", "body": "B", "push_data": None}
            for i in range(3)
        ]
        client.rpc_responses["claim_push_delivery_retries"] = claimed_rows

        with patch("app.services.push_delivery.send_fcm_notification", return_value={"ok": True, "response": {}}):
            counts = process_retry_batch(client, batch_size=3)
        assert counts["claimed"] == 3
        assert counts["delivered"] == 3

    def test_batch_skips_rows_with_future_next_retry_at(self):
        client = FakeDeliveryClient()
        client.rpc_responses["claim_push_delivery_retries"] = []
        with patch("app.services.push_delivery.send_fcm_notification"):
            counts = process_retry_batch(client, batch_size=10)
        assert counts["claimed"] == 0

    def test_batch_returns_zero_when_no_eligible_rows(self):
        client = FakeDeliveryClient()
        client.rpc_responses["claim_push_delivery_retries"] = []
        with patch("app.services.push_delivery.send_fcm_notification"):
            counts = process_retry_batch(client, batch_size=10)
        assert counts["claimed"] == 0
        assert counts["delivered"] == 0
