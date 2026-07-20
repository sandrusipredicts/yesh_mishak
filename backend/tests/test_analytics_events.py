from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from app.rate_limit import get_limiter


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]
    count: int | None = None


class FakeTableQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, Any]] = []
        self.inserted: list[dict[str, Any]] | None = None
        self.exact_count = False

    def select(self, _: str = "*", count: str | None = None) -> "FakeTableQuery":
        self.exact_count = count == "exact"
        return self

    def eq(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append((column, value))
        return self

    def gte(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append(("__gte", (column, value)))
        return self

    def lt(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append(("__lt", (column, value)))
        return self

    def limit(self, _: int) -> "FakeTableQuery":
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> "FakeTableQuery":
        self.inserted = [dict(row) for row in payload] if isinstance(payload, list) else [dict(payload)]
        return self

    def execute(self) -> FakeResponse:
        if self.inserted is not None:
            self.rows.extend(dict(row) for row in self.inserted)
            return FakeResponse([dict(row) for row in self.inserted])

        rows = self.rows
        for column, value in self.filters:
            if column == "__gte":
                col, threshold = value
                rows = [row for row in rows if (row.get(col) or "") >= threshold]
            elif column == "__lt":
                col, threshold = value
                rows = [row for row in rows if (row.get(col) or "") < threshold]
            else:
                rows = [row for row in rows if row.get(column) == value]
        return FakeResponse([dict(row) for row in rows], len(rows) if self.exact_count else None)


class FakeSupabaseClient:
    def __init__(self, user: dict[str, Any], *, fail_analytics_insert: bool = False) -> None:
        self.tables = {
            "users": [user],
            "analytics_events": [],
            "api_request_metrics": [],
        }
        self.fail_analytics_insert = fail_analytics_insert

    def table(self, table_name: str) -> FakeTableQuery:
        if table_name == "analytics_events" and self.fail_analytics_insert:
            raise RuntimeError("analytics events table unavailable")
        return FakeTableQuery(self.tables.setdefault(table_name, []))


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def make_user() -> dict[str, Any]:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "user@example.com",
        "name": "User",
        "role": "user",
        "status": "active",
    }


def make_client(monkeypatch, *, fail_analytics_insert: bool = False) -> tuple[TestClient, FakeSupabaseClient, dict[str, Any]]:
    configure_test_settings(monkeypatch)
    user = make_user()
    fake_client = FakeSupabaseClient(user, fail_analytics_insert=fail_analytics_insert)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.services.analytics_events.get_supabase_service_role_client",
        lambda: fake_client,
    )
    monkeypatch.setattr(
        "app.services.api_request_metrics.get_supabase_service_role_client",
        lambda: fake_client,
    )
    return TestClient(app), fake_client, user


def post_events(client: TestClient, user: dict[str, Any], events: list[dict[str, Any]]):
    return client.post(
        "/analytics/events",
        json={"events": events},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )


def app_open_event(**overrides: Any) -> dict[str, Any]:
    return {
        "event_name": "app_open",
        "platform": "android",
        **overrides,
    }


def screen_view_event(**overrides: Any) -> dict[str, Any]:
    return {
        "event_name": "screen_view",
        "platform": "web",
        "properties": {"screen": "map"},
        **overrides,
    }


# --- Ingestion: valid payloads -------------------------------------------


def test_valid_batch_persists_all_events(monkeypatch) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_events(client, user, [app_open_event(), screen_view_event()])

    assert response.status_code == 202
    assert response.json() == {"accepted": 2, "rejected": 0}
    assert fake_client.tables["analytics_events"] == [
        {"event_name": "app_open", "platform": "android", "properties": {}},
        {"event_name": "screen_view", "platform": "web", "properties": {"screen": "map"}},
    ]


@pytest.mark.parametrize("screen", ["map", "game_details", "profile", "notifications", "admin"])
def test_every_approved_screen_value_is_accepted(monkeypatch, screen: str) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_events(client, user, [screen_view_event(properties={"screen": screen})])

    assert response.status_code == 202
    assert response.json() == {"accepted": 1, "rejected": 0}
    assert fake_client.tables["analytics_events"][0]["properties"] == {"screen": screen}


def test_recent_client_timestamp_is_persisted_as_recorded_at(monkeypatch) -> None:
    client, fake_client, user = make_client(monkeypatch)
    occurred_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    response = post_events(client, user, [app_open_event(occurred_at=occurred_at)])

    assert response.status_code == 202
    assert fake_client.tables["analytics_events"][0]["recorded_at"] == occurred_at


@pytest.mark.parametrize(
    "occurred_at",
    [
        (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    ],
)
def test_absurd_client_timestamps_are_discarded_so_server_default_wins(monkeypatch, occurred_at: str) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_events(client, user, [app_open_event(occurred_at=occurred_at)])

    assert response.status_code == 202
    assert response.json() == {"accepted": 1, "rejected": 0}
    assert "recorded_at" not in fake_client.tables["analytics_events"][0]


# --- Ingestion: registry validation matrix -------------------------------


@pytest.mark.parametrize(
    "event",
    [
        app_open_event(event_name="app_opened"),
        app_open_event(event_name="game_created"),
        app_open_event(platform="desktop"),
        app_open_event(properties={"screen": "map"}),
        screen_view_event(properties={}),
        screen_view_event(properties={"screen": "dashboard"}),
        screen_view_event(properties={"screen": "map", "extra": "value"}),
        screen_view_event(properties={"screen": 42}),
    ],
)
def test_registry_violations_are_rejected_not_persisted(monkeypatch, event: dict[str, Any]) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_events(client, user, [event])

    assert response.status_code == 202
    assert response.json() == {"accepted": 0, "rejected": 1}
    assert fake_client.tables["analytics_events"] == []


@pytest.mark.parametrize(
    "field_name",
    ["user_id", "user_hash", "email", "game_id", "field_id", "url", "latitude", "metadata"],
)
def test_prohibited_and_unexpected_envelope_fields_are_rejected(monkeypatch, field_name: str) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_events(client, user, [app_open_event(**{field_name: "prohibited"})])

    assert response.status_code == 202
    assert response.json() == {"accepted": 0, "rejected": 1}
    assert fake_client.tables["analytics_events"] == []


def test_partial_acceptance_persists_only_valid_events(monkeypatch) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_events(
        client,
        user,
        [
            app_open_event(),
            screen_view_event(properties={"screen": "dashboard"}),
            screen_view_event(properties={"screen": "profile"}),
        ],
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": 2, "rejected": 1}
    assert [row["event_name"] for row in fake_client.tables["analytics_events"]] == [
        "app_open",
        "screen_view",
    ]


# --- Ingestion: batch envelope -------------------------------------------


def test_batch_over_20_events_is_rejected_entirely(monkeypatch) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_events(client, user, [app_open_event()] * 21)

    assert response.status_code == 422
    assert fake_client.tables["analytics_events"] == []


def test_empty_batch_is_rejected(monkeypatch) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_events(client, user, [])

    assert response.status_code == 422
    assert fake_client.tables["analytics_events"] == []


def test_structurally_malformed_body_is_rejected(monkeypatch) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = client.post(
        "/analytics/events",
        json={"events": "not-a-list"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )

    assert response.status_code == 422
    assert fake_client.tables["analytics_events"] == []


# --- Auth + rate limits --------------------------------------------------


def test_requires_authenticated_user(monkeypatch) -> None:
    client, fake_client, _ = make_client(monkeypatch)

    response = client.post("/analytics/events", json={"events": [app_open_event()]})

    assert response.status_code == 401
    assert fake_client.tables["analytics_events"] == []


def test_minute_window_rate_limit_applies_per_user(monkeypatch) -> None:
    client, _, user = make_client(monkeypatch)

    for _ in range(30):
        assert post_events(client, user, [app_open_event()]).status_code == 202

    response = post_events(client, user, [app_open_event()])

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"


def test_hourly_window_rate_limit_applies_per_user(monkeypatch) -> None:
    client, _, user = make_client(monkeypatch)
    limiter = get_limiter()
    fake_clock = {"now": 1000.0}
    limiter.set_clock(lambda: fake_clock["now"])

    accepted = 0
    while accepted < 200:
        assert post_events(client, user, [app_open_event()]).status_code == 202
        accepted += 1
        if accepted % 30 == 0:
            # Stay under the 30/min limit; total elapsed stays inside the hour.
            fake_clock["now"] += 61

    fake_clock["now"] += 61
    response = post_events(client, user, [app_open_event()])

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"


# --- Persistence failure -------------------------------------------------


def test_persistence_failure_returns_unavailable_without_leaking_payload(monkeypatch, caplog) -> None:
    client, _, user = make_client(monkeypatch, fail_analytics_insert=True)

    response = post_events(client, user, [app_open_event()])

    assert response.status_code == 503
    assert response.json()["code"] == "ANALYTICS_UNAVAILABLE"
    assert "00000000" not in caplog.text
    assert "https://" not in caplog.text


# --- Admin monitoring degradation ----------------------------------------


def _window() -> tuple[datetime, datetime]:
    ended = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    return ended - timedelta(minutes=60), ended


def test_admin_monitoring_section_reports_grouped_metrics(monkeypatch) -> None:
    import app.api.admin as admin

    rows = [
        {"event_day": "2026-07-20", "event_name": "app_open", "platform": "android", "event_count": 3},
        {"event_day": "2026-07-20", "event_name": "screen_view", "platform": "web", "event_count": 5},
    ]
    monkeypatch.setattr(admin, "get_analytics_event_metrics", lambda **_: rows)
    window_started_at, window_ended_at = _window()

    result = admin._get_analytics_event_monitoring(
        window_minutes=60,
        window_started_at=window_started_at,
        window_ended_at=window_ended_at,
    )

    assert result["source_available"] is True
    assert result["status"] == "ok"
    assert result["total_events"] == 8
    assert result["groups"] == rows


def test_admin_monitoring_section_degrades_when_migration_missing(monkeypatch) -> None:
    import app.api.admin as admin

    def raise_missing_table(**_: Any) -> None:
        raise RuntimeError("relation analytics_events does not exist")

    monkeypatch.setattr(admin, "get_analytics_event_metrics", raise_missing_table)
    window_started_at, window_ended_at = _window()

    result = admin._get_analytics_event_monitoring(
        window_minutes=60,
        window_started_at=window_started_at,
        window_ended_at=window_ended_at,
    )

    assert result["source_available"] is False
    assert result["status"] == "unavailable"
    assert "analytics_events.sql" in result["reason"]


# --- Service layer: RPC wrapper coercion ----------------------------------


class FakeRpcQuery:
    def __init__(self, data: Any) -> None:
        self.data = data

    def execute(self) -> Any:
        return FakeResponse(self.data)


class FakeRpcClient:
    def __init__(self, data: Any = None) -> None:
        self.data = data
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, function_name: str, params: dict[str, Any]) -> FakeRpcQuery:
        self.calls.append((function_name, dict(params)))
        return FakeRpcQuery(self.data)


def get_metrics_with(data: Any) -> tuple[list[dict[str, Any]], FakeRpcClient]:
    from app.services.analytics_events import get_analytics_event_metrics

    window_started_at, window_ended_at = _window()
    client = FakeRpcClient(data)
    rows = get_analytics_event_metrics(
        window_started_at=window_started_at,
        window_ended_at=window_ended_at,
        supabase=client,
    )
    return rows, client


@pytest.mark.parametrize("data", [None, {"unexpected": "shape"}, "not-a-list", 42])
def test_metrics_wrapper_returns_empty_list_for_non_list_rpc_data(data: Any) -> None:
    rows, _ = get_metrics_with(data)

    assert rows == []


def test_metrics_wrapper_skips_rows_that_are_not_dicts() -> None:
    valid = {"event_day": "2026-07-20", "event_name": "app_open", "platform": "web", "event_count": 2}

    rows, _ = get_metrics_with([None, "garbage", 7, ["nested"], valid])

    assert rows == [
        {"event_day": "2026-07-20", "event_name": "app_open", "platform": "web", "event_count": 2},
    ]


@pytest.mark.parametrize(
    ("raw_row", "expected"),
    [
        (
            {"event_day": None, "event_name": None, "platform": None, "event_count": None},
            {"event_day": "", "event_name": "", "platform": "", "event_count": 0},
        ),
        (
            {},
            {"event_day": "", "event_name": "", "platform": "", "event_count": 0},
        ),
        (
            {"event_day": "2026-07-20", "event_name": "app_open", "platform": "web", "event_count": "garbage"},
            {"event_day": "2026-07-20", "event_name": "app_open", "platform": "web", "event_count": 0},
        ),
        (
            {"event_day": "2026-07-20", "event_name": "app_open", "platform": "web", "event_count": -3},
            {"event_day": "2026-07-20", "event_name": "app_open", "platform": "web", "event_count": 0},
        ),
        (
            {"event_day": "2026-07-20", "event_name": "app_open", "platform": "web", "event_count": "12"},
            {"event_day": "2026-07-20", "event_name": "app_open", "platform": "web", "event_count": 12},
        ),
    ],
)
def test_metrics_wrapper_coerces_malformed_row_fields(
    raw_row: dict[str, Any], expected: dict[str, Any],
) -> None:
    rows, _ = get_metrics_with([raw_row])

    assert rows == [expected]


def test_metrics_wrapper_passes_iso_window_to_the_rpc() -> None:
    window_started_at, window_ended_at = _window()

    _, client = get_metrics_with([])

    assert client.calls == [
        (
            "get_analytics_event_metrics",
            {
                "window_start": window_started_at.isoformat(),
                "window_end": window_ended_at.isoformat(),
            },
        ),
    ]


@pytest.mark.parametrize("retention_days", [0, 366, -1])
def test_cleanup_service_rejects_out_of_bounds_retention_before_any_rpc(retention_days: int) -> None:
    from app.services.analytics_events import cleanup_analytics_events

    client = FakeRpcClient(0)

    with pytest.raises(ValueError):
        cleanup_analytics_events(retention_days=retention_days, supabase=client)

    assert client.calls == []


@pytest.mark.parametrize(
    ("rpc_data", "expected"),
    [
        (5, 5),
        ("12", 12),
        (None, 0),
        ("garbage", 0),
        (-4, 0),
    ],
)
def test_cleanup_service_coerces_rpc_response_to_non_negative_int(
    rpc_data: Any, expected: int,
) -> None:
    from app.services.analytics_events import cleanup_analytics_events

    client = FakeRpcClient(rpc_data)

    assert cleanup_analytics_events(retention_days=30, supabase=client) == expected


def test_cleanup_service_calls_the_rpc_with_retention_days() -> None:
    from app.services.analytics_events import cleanup_analytics_events

    client = FakeRpcClient(1)
    cleanup_analytics_events(retention_days=45, supabase=client)

    assert client.calls == [("cleanup_analytics_events", {"retention_days": 45})]


# --- Cleanup job (app/jobs/cleanup_analytics_events.py) -------------------


class FakeJobRun:
    def __init__(self) -> None:
        self.id = "run-1"


class FakeRecorder:
    def __init__(
        self,
        *,
        fail_start: bool = False,
        fail_mark_succeeded: bool = False,
    ) -> None:
        self.fail_start = fail_start
        self.fail_mark_succeeded = fail_mark_succeeded
        self.started_job_name: str | None = None
        self.started_metadata: dict[str, Any] | None = None
        self.succeeded = False
        self.failed = False
        self.result: dict[str, Any] | None = None
        self.exc: BaseException | None = None

    def start(self, *, job_name: str, metadata: dict[str, Any] | None = None) -> FakeJobRun:
        if self.fail_start:
            raise RuntimeError("job_runs table unavailable")
        self.started_job_name = job_name
        self.started_metadata = dict(metadata or {})
        return FakeJobRun()

    def mark_succeeded(self, job_run: Any, result: dict[str, Any]) -> None:
        if self.fail_mark_succeeded:
            raise RuntimeError("job_runs update unavailable")
        self.succeeded = True
        self.result = dict(result)

    def mark_failed(self, job_run: Any, exc: BaseException) -> None:
        self.failed = True
        self.exc = exc


def run_cleanup_job(
    argv: list[str],
    *,
    recorder: FakeRecorder | None = None,
    cleanup_return: int = 0,
    cleanup_side_effect: BaseException | None = None,
) -> tuple[int, FakeRecorder, Any]:
    from app.jobs.cleanup_analytics_events import main

    recorder = recorder or FakeRecorder()
    cleanup_kwargs: dict[str, Any] = (
        {"side_effect": cleanup_side_effect}
        if cleanup_side_effect is not None
        else {"return_value": cleanup_return}
    )
    with patch(
        "app.jobs.cleanup_analytics_events.JobRunRecorder",
        return_value=recorder,
    ), patch(
        "app.jobs.cleanup_analytics_events.cleanup_analytics_events",
        **cleanup_kwargs,
    ) as cleanup_mock:
        exit_code = main(argv)
    return exit_code, recorder, cleanup_mock


def test_cleanup_job_success_prints_json_result_and_exits_zero(capsys) -> None:
    exit_code, _, _ = run_cleanup_job([], cleanup_return=7)

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "deleted_count": 7,
        "retention_days": 90,
    }


def test_cleanup_job_records_job_run_start_and_success(capsys) -> None:
    exit_code, recorder, _ = run_cleanup_job(["--retention-days", "30"], cleanup_return=3)

    assert exit_code == 0
    assert recorder.started_job_name == "analytics_events_cleanup"
    assert recorder.started_metadata == {
        "retention_days": 30,
        "entry_point": "app.jobs.cleanup_analytics_events",
    }
    assert recorder.succeeded
    assert recorder.failed is False
    assert recorder.result == {"deleted_count": 3, "retention_days": 30}


def test_cleanup_job_service_failure_marks_failed_and_exits_one(capsys) -> None:
    boom = RuntimeError("cleanup rpc unavailable")

    exit_code, recorder, _ = run_cleanup_job([], cleanup_side_effect=boom)

    assert exit_code == 1
    assert recorder.failed
    assert recorder.exc is boom
    assert recorder.succeeded is False
    assert capsys.readouterr().out == ""


def test_cleanup_job_recorder_start_failure_is_non_fatal(capsys) -> None:
    recorder = FakeRecorder(fail_start=True)

    exit_code, recorder, cleanup_mock = run_cleanup_job(
        [], recorder=recorder, cleanup_return=2,
    )

    assert exit_code == 0
    cleanup_mock.assert_called_once_with(retention_days=90)
    assert json.loads(capsys.readouterr().out)["deleted_count"] == 2


def test_cleanup_job_recorder_finalize_failure_is_non_fatal(capsys) -> None:
    recorder = FakeRecorder(fail_mark_succeeded=True)

    exit_code, _, _ = run_cleanup_job([], recorder=recorder, cleanup_return=1)

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["deleted_count"] == 1


@pytest.mark.parametrize("retention_days", ["0", "366", "-5", "not-a-number"])
def test_cleanup_job_rejects_out_of_bounds_retention_days(capsys, retention_days: str) -> None:
    from app.jobs.cleanup_analytics_events import main

    with patch(
        "app.jobs.cleanup_analytics_events.cleanup_analytics_events",
    ) as cleanup_mock, patch(
        "app.jobs.cleanup_analytics_events.JobRunRecorder",
        return_value=FakeRecorder(),
    ):
        with pytest.raises(SystemExit) as excinfo:
            main(["--retention-days", retention_days])

    assert excinfo.value.code == 2
    cleanup_mock.assert_not_called()


def test_cleanup_job_defaults_to_ninety_day_retention(capsys) -> None:
    exit_code, recorder, cleanup_mock = run_cleanup_job([], cleanup_return=0)

    assert exit_code == 0
    cleanup_mock.assert_called_once_with(retention_days=90)
    assert recorder.started_metadata == {
        "retention_days": 90,
        "entry_point": "app.jobs.cleanup_analytics_events",
    }
