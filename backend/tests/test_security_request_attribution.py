from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any
from uuid import UUID

import pytest

from app.services import security_request_attribution as attribution
from app.services.security_attribution_config import (
    ActiveSecurityAttributionConfiguration,
    SecurityAttributionRuntimeConfiguration,
)


ACCOUNT_UUID = UUID("00000000-0000-4000-8000-000000000001")
EVENT_ID = UUID("00000000-0000-4000-8000-000000001031")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000001032")
NOW = datetime(2026, 7, 31, 12, 34, 56, 789000, tzinfo=timezone.utc)
KEY_BYTES = bytes(range(32))
EXPECTED_PSEUDONYM = "yXFDc5fbHJ_5UKP5B6AC3mJspD7YWmec18R0PtMmO8w"


@dataclass
class FakeResponse:
    data: Any


class FakeRpcCall:
    def __init__(self, client: "FakeServiceRoleClient") -> None:
        self.client = client

    def execute(self) -> FakeResponse:
        if self.client.error is not None:
            raise self.client.error
        if self.client.responses:
            return FakeResponse(self.client.responses.pop(0))
        return FakeResponse("inserted")


class FakeServiceRoleClient:
    def __init__(
        self,
        *,
        responses: list[Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.table_calls = 0

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpcCall:
        self.rpc_calls.append((name, dict(params)))
        return FakeRpcCall(self)

    def table(self, _name: str) -> None:
        self.table_calls += 1
        raise AssertionError("direct table access is forbidden")


def active_runtime(
    *,
    epoch: str = "2026-07",
    key_material: bytes = KEY_BYTES,
) -> SecurityAttributionRuntimeConfiguration:
    return SecurityAttributionRuntimeConfiguration(
        enabled=True,
        active=ActiveSecurityAttributionConfiguration(
            environment="development",
            epoch=epoch,
            key_version=1,
            key_material=key_material,
        ),
    )


def build_recorder(
    fake: FakeServiceRoleClient,
    *,
    runtime: SecurityAttributionRuntimeConfiguration | None = None,
) -> attribution.SecurityAttributionRecorder:
    return attribution.SecurityAttributionRecorder(
        configuration_provider=lambda: runtime or active_runtime(),
        service_role_client_factory=lambda timeout: (
            fake
            if timeout == attribution.SECURITY_ATTRIBUTION_RPC_TIMEOUT_SECONDS
            else (_ for _ in ()).throw(AssertionError("unexpected timeout"))
        ),
        clock=lambda: NOW,
    )


def create_event(
    recorder: attribution.SecurityAttributionRecorder,
    **overrides: Any,
) -> attribution.SecurityAttributionEventRequest:
    values: dict[str, Any] = {
        "trusted_account_uuid": ACCOUNT_UUID,
        "route_key": "auth_logout",
        "event_category": "session_security_change",
        "http_method": "POST",
        "outcome": "succeeded",
        "failure_category": None,
        "server_correlation_id": CORRELATION_ID,
        "request_event_id": EVENT_ID,
    }
    values.update(overrides)
    return recorder.create_event(**values)


def test_recorder_uses_one_config_snapshot_and_expected_pseudonym() -> None:
    fake = FakeServiceRoleClient(responses=["inserted"])
    provider_calls = 0

    def configuration_provider() -> SecurityAttributionRuntimeConfiguration:
        nonlocal provider_calls
        provider_calls += 1
        return active_runtime()

    recorder = attribution.SecurityAttributionRecorder(
        configuration_provider=configuration_provider,
        service_role_client_factory=lambda _timeout: fake,
        clock=lambda: NOW,
    )

    result = recorder.record(create_event(recorder))

    assert result.status == "inserted"
    assert provider_calls == 1
    payload = fake.rpc_calls[0][1]
    assert payload["p_account_pseudonym"] == EXPECTED_PSEUDONYM
    assert payload["p_environment"] == "development"
    assert payload["p_pseudonym_epoch"] == "2026-07"
    assert payload["p_pseudonym_key_version"] == 1


def test_recorder_calls_only_ingestion_rpc_through_service_role_factory() -> None:
    fake = FakeServiceRoleClient(responses=[["inserted"]])
    service_role_calls = 0

    def service_role_factory(timeout: float) -> FakeServiceRoleClient:
        nonlocal service_role_calls
        service_role_calls += 1
        assert timeout == 2.0
        return fake

    recorder = attribution.SecurityAttributionRecorder(
        configuration_provider=active_runtime,
        service_role_client_factory=service_role_factory,
        clock=lambda: NOW,
    )

    assert recorder.record(create_event(recorder)).status == "inserted"
    assert service_role_calls == 1
    assert fake.rpc_calls[0][0] == "record_security_request_attribution_event"
    assert fake.table_calls == 0


def test_rpc_payload_is_exact_and_contains_no_raw_account_or_pii() -> None:
    fake = FakeServiceRoleClient()
    recorder = build_recorder(fake)

    recorder.record(create_event(recorder))

    payload = fake.rpc_calls[0][1]
    assert set(payload) == {
        "p_request_event_id",
        "p_occurred_at",
        "p_account_pseudonym",
        "p_pseudonym_epoch",
        "p_pseudonym_key_version",
        "p_environment",
        "p_event_category",
        "p_route_key",
        "p_http_method",
        "p_outcome",
        "p_failure_category",
        "p_server_correlation_id",
    }
    serialized = repr(payload)
    assert str(ACCOUNT_UUID) not in serialized
    for forbidden in (
        "email",
        "username",
        "phone",
        "ip",
        "user_agent",
        "header",
        "cookie",
        "token",
        "query",
        "url",
        "body",
    ):
        assert forbidden not in " ".join(payload).lower()


@pytest.mark.parametrize("rpc_result", ["inserted", ["inserted"]])
def test_recorder_handles_inserted(rpc_result: Any) -> None:
    fake = FakeServiceRoleClient(responses=[rpc_result])
    recorder = build_recorder(fake)

    assert recorder.record(create_event(recorder)).status == "inserted"


@pytest.mark.parametrize("rpc_result", ["already_recorded", ["already_recorded"]])
def test_recorder_handles_already_recorded(rpc_result: Any) -> None:
    fake = FakeServiceRoleClient(responses=[rpc_result])
    recorder = build_recorder(fake)

    assert recorder.record(create_event(recorder)).status == "already_recorded"


@pytest.mark.parametrize(
    "rpc_result",
    [None, "unknown", [], ["inserted", "already_recorded"], {}, True, 1],
)
def test_recorder_rejects_unexpected_rpc_response(rpc_result: Any) -> None:
    fake = FakeServiceRoleClient(responses=[rpc_result])
    recorder = build_recorder(fake)

    with pytest.raises(attribution.SecurityAttributionRecorderError) as exc_info:
        recorder.record(create_event(recorder))

    assert exc_info.value.failure_category == "unexpected_rpc_response"


def test_supabase_failure_maps_to_bounded_recorder_failure() -> None:
    fake = FakeServiceRoleClient(error=RuntimeError("database secret detail"))
    recorder = build_recorder(fake)

    with pytest.raises(attribution.SecurityAttributionRecorderError) as exc_info:
        recorder.record(create_event(recorder))

    assert exc_info.value.failure_category == "ingestion_rpc_failed"
    assert str(exc_info.value) == "security attribution recording failed"
    assert "database secret detail" not in repr(exc_info.value)


def test_conflicting_replay_is_a_bounded_ingestion_failure() -> None:
    class ConflictError(RuntimeError):
        code = "23505"

    fake = FakeServiceRoleClient(error=ConflictError("immutable payload conflict"))
    recorder = build_recorder(fake)

    with pytest.raises(attribution.SecurityAttributionRecorderError) as exc_info:
        recorder.record(create_event(recorder))

    assert exc_info.value.failure_category == "ingestion_rpc_failed"
    assert "immutable payload conflict" not in str(exc_info.value)


def test_pseudonym_failure_maps_to_bounded_recorder_failure() -> None:
    fake = FakeServiceRoleClient()
    recorder = build_recorder(fake, runtime=active_runtime(key_material=b"A" * 32))

    with pytest.raises(attribution.SecurityAttributionRecorderError) as exc_info:
        recorder.record(create_event(recorder))

    assert exc_info.value.failure_category == "pseudonym_derivation_failed"
    assert fake.rpc_calls == []


def test_event_timestamp_must_match_configured_epoch() -> None:
    fake = FakeServiceRoleClient()
    recorder = build_recorder(fake, runtime=active_runtime(epoch="2026-06"))

    with pytest.raises(attribution.SecurityAttributionRecorderError) as exc_info:
        recorder.record(create_event(recorder))

    assert exc_info.value.failure_category == "invalid_configuration"
    assert fake.rpc_calls == []


def test_same_immutable_event_is_idempotent() -> None:
    fake = FakeServiceRoleClient(responses=["inserted", "already_recorded"])
    recorder = build_recorder(fake)
    event = create_event(recorder)

    assert recorder.record(event).status == "inserted"
    assert recorder.record(event).status == "already_recorded"
    assert fake.rpc_calls[0] == fake.rpc_calls[1]


def test_disabled_recorder_is_safe_noop_without_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        attribution,
        "get_security_attribution_runtime_configuration",
        lambda: attribution.SecurityAttributionRuntimeConfiguration(
            enabled=False,
            active=None,
        ),
    )
    monkeypatch.setattr(
        attribution,
        "get_supabase_service_role_client",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled recorder must not create a client")
        ),
    )

    with caplog.at_level(logging.WARNING, logger=attribution.__name__):
        result = attribution.record_authenticated_security_event(
            trusted_account_uuid=ACCOUNT_UUID,
            route_key="auth_logout",
            event_category="session_security_change",
            http_method="POST",
            outcome="succeeded",
            failure_category=None,
            server_correlation_id=CORRELATION_ID,
        )

    assert result.status == "disabled"
    assert caplog.records == []


def test_fail_open_warning_and_monitoring_are_privacy_bounded(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    exception_secret = "exception=email@example.com token=secret-token"
    fake = FakeServiceRoleClient(error=RuntimeError(exception_secret))
    monitoring_calls: list[dict[str, Any]] = []
    current_epoch = datetime.now(timezone.utc).strftime("%Y-%m")
    monkeypatch.setattr(
        attribution,
        "get_security_attribution_runtime_configuration",
        lambda: active_runtime(epoch=current_epoch),
    )
    monkeypatch.setattr(
        attribution,
        "get_supabase_service_role_client",
        lambda **_kwargs: fake,
    )
    monkeypatch.setattr(
        attribution,
        "safe_auth_monitor",
        lambda message, level="warning", **tags: monitoring_calls.append(
            {"message": message, "level": level, "tags": tags}
        ),
    )

    with caplog.at_level(logging.WARNING, logger=attribution.__name__):
        result = attribution.record_authenticated_security_event(
            trusted_account_uuid=ACCOUNT_UUID,
            route_key="auth_logout",
            event_category="session_security_change",
            http_method="POST",
            outcome="succeeded",
            failure_category=None,
            server_correlation_id=CORRELATION_ID,
        )

    assert result.status == "failed"
    assert result.failure_category == "ingestion_rpc_failed"
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert len(monitoring_calls) == 1
    assert warnings[0].recorder_failure_category == "ingestion_rpc_failed"
    assert set(monitoring_calls[0]["tags"]) == {
        "recorder_failure_category",
        "route_key",
        "event_category",
        "http_method",
        "environment",
    }

    diagnostics = repr(warnings[0].__dict__) + repr(monitoring_calls)
    for sensitive_value in (
        exception_secret,
        str(ACCOUNT_UUID),
        str(CORRELATION_ID),
        EXPECTED_PSEUDONYM,
        repr(KEY_BYTES),
        "email@example.com",
        "secret-token",
    ):
        assert sensitive_value not in diagnostics


def test_event_repr_redacts_raw_uuid_and_event_identifiers() -> None:
    recorder = build_recorder(FakeServiceRoleClient())
    representation = repr(create_event(recorder))

    assert str(ACCOUNT_UUID) not in representation
    assert str(EVENT_ID) not in representation
    assert str(CORRELATION_ID) not in representation
    assert representation.count("[REDACTED]") == 3


def test_unsupported_route_tuple_cannot_be_recorded() -> None:
    fake = FakeServiceRoleClient()
    recorder = build_recorder(fake)

    with pytest.raises(
        attribution.SecurityAttributionEventValidationError,
        match=r"^security attribution route tuple is unsupported$",
    ):
        create_event(
            recorder,
            route_key="synthetic_unsupported_route",
            event_category="synthetic_unsupported_category",
        )

    forged_event = attribution.SecurityAttributionEventRequest(
        request_event_id=EVENT_ID,
        occurred_at=NOW,
        trusted_account_uuid=ACCOUNT_UUID,
        event_category="synthetic_unsupported_category",
        route_key="synthetic_unsupported_route",
        http_method="POST",
        outcome="succeeded",
        failure_category=None,
        server_correlation_id=CORRELATION_ID,
    )
    with pytest.raises(
        attribution.SecurityAttributionEventValidationError,
        match=r"^security attribution route tuple is unsupported$",
    ):
        recorder.record(forged_event)

    assert fake.rpc_calls == []
