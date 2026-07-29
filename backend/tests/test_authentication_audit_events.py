from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import pytest

from app.core.config import get_settings
from app.services import authentication_audit_events as audit
from app.services import authentication_observability as auth_observability


@dataclass
class FakeResponse:
    data: Any


class FakeRpcCall:
    def __init__(self, client: "FakeAuditClient", params: dict[str, Any]) -> None:
        self.client = client
        self.params = params

    def execute(self) -> FakeResponse:
        if self.client.error is not None:
            raise self.client.error
        event_id = self.params["p_event_id"]
        inserted = event_id not in self.client.event_ids
        self.client.event_ids.add(event_id)
        return FakeResponse(self.client.response_shape(inserted))


class FakeAuditClient:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        response_shape=lambda value: value,
    ) -> None:
        self.error = error
        self.response_shape = response_shape
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.event_ids: set[str] = set()

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpcCall:
        self.rpc_calls.append((name, dict(params)))
        return FakeRpcCall(self, params)


def configure_settings(monkeypatch, environment: str = "test") -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "public-test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-test-client")
    monkeypatch.setenv("JWT_SECRET", "jwt-test-secret")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", environment)
    get_settings.cache_clear()


def test_exact_rpc_payload_uses_service_role_and_normalized_environment(monkeypatch) -> None:
    configure_settings(monkeypatch, environment="  Preview / EU West !!!  ")
    fake = FakeAuditClient(response_shape=lambda value: [value])
    service_role_calls = 0

    def get_service_role_client() -> FakeAuditClient:
        nonlocal service_role_calls
        service_role_calls += 1
        return fake

    monkeypatch.setattr(audit, "get_supabase_service_role_client", get_service_role_client)

    inserted = audit.record_authentication_event(
        event_id="00000000-0000-4000-8000-000000001031",
        event_type="login",
        outcome="failed",
        auth_method="password",
        correlation_id="correlation-1031",
        user_id="00000000-0000-4000-8000-000000001032",
        failure_category="invalid_credentials",
    )

    assert inserted is True
    assert service_role_calls == 1
    assert fake.rpc_calls == [
        (
            "record_authentication_audit_event",
            {
                "p_event_id": "00000000-0000-4000-8000-000000001031",
                "p_event_type": "login",
                "p_outcome": "failed",
                "p_auth_method": "password",
                "p_user_id": "00000000-0000-4000-8000-000000001032",
                "p_failure_category": "invalid_credentials",
                "p_revocation_reason": None,
                "p_correlation_id": "correlation-1031",
                "p_source_environment": "preview-eu-west",
            },
        )
    ]


def test_duplicate_retry_reuses_event_id_and_is_idempotent(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake = FakeAuditClient()
    monkeypatch.setattr(audit, "get_supabase_service_role_client", lambda: fake)
    kwargs = {
        "event_id": "00000000-0000-4000-8000-000000001031",
        "event_type": "login",
        "outcome": "succeeded",
        "auth_method": "google",
        "correlation_id": "correlation-1031",
        "user_id": "00000000-0000-4000-8000-000000001032",
    }

    assert audit.record_authentication_event(**kwargs) is True
    assert audit.record_authentication_event(**kwargs) is False
    assert fake.rpc_calls[0] == fake.rpc_calls[1]


@pytest.mark.parametrize(
    "malformed_response",
    [
        [],
        [True, False],
        None,
        {},
        "true",
        1,
        0,
        [1],
        {"result": True},
    ],
    ids=[
        "empty-list",
        "multi-element-list",
        "none",
        "dictionary",
        "string",
        "integer-one",
        "integer-zero",
        "single-non-boolean",
        "result-dictionary",
    ],
)
def test_malformed_rpc_response_warns_once_and_remains_non_fatal(
    monkeypatch,
    caplog,
    malformed_response: Any,
) -> None:
    configure_settings(monkeypatch)
    fake = FakeAuditClient(response_shape=lambda _value: malformed_response)
    monitoring_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(audit, "get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr(
        auth_observability,
        "capture_unexpected_message",
        lambda message, level="warning", **tags: monitoring_calls.append(
            {"message": message, "level": level, "tags": tags}
        ),
    )

    with caplog.at_level(logging.WARNING, logger=audit.__name__):
        inserted = audit.record_authentication_event(
            event_id="00000000-0000-4000-8000-000000001031",
            event_type="login",
            outcome="succeeded",
            auth_method="password",
            correlation_id="correlation-1031",
        )

    assert inserted is False
    warnings = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.audit.persist.failure"
    ]
    assert len(warnings) == 1
    assert warnings[0].error_category == "unexpected_response"
    assert len(monitoring_calls) == 1
    assert monitoring_calls[0]["tags"]["error_category"] == "unexpected_response"


def test_persistence_warning_is_sanitized_and_monitoring_has_no_high_cardinality_tags(
    monkeypatch,
    caplog,
) -> None:
    configure_settings(monkeypatch)
    sentinels = (
        "password=personal-secret",
        "access_token=access-secret",
        "refresh_token=refresh-secret",
        "Authorization=Bearer bearer-secret",
        "email=person@example.com",
        "username=private-user",
        "ip=203.0.113.42",
        "provider_subject=google-private-subject",
    )
    fake = FakeAuditClient(error=RuntimeError(" ".join(sentinels)))
    monitoring_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(audit, "get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr(
        auth_observability,
        "capture_unexpected_message",
        lambda message, level="warning", **tags: monitoring_calls.append(
            {"message": message, "level": level, "tags": tags}
        ),
    )

    with caplog.at_level(logging.WARNING, logger=audit.__name__):
        inserted = audit.record_authentication_event(
            event_id="00000000-0000-4000-8000-000000001031",
            event_type="login",
            outcome="failed",
            auth_method="google",
            correlation_id="correlation-1031",
            failure_category="invalid_provider_credential",
        )

    assert inserted is False
    warning = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.audit.persist.failure"
    )
    assert warning.exception_type == "RuntimeError"
    assert warning.user_id_present is False
    assert monitoring_calls == [
        {
            "message": "Authentication audit event persistence failed",
            "level": "warning",
            "tags": {
                "event": "auth.audit.persist.failure",
                "audit_event_type": "login",
                "outcome": "failed",
                "auth_method": "google",
                "failure_category": "invalid_provider_credential",
                "revocation_reason": None,
                "environment": "test",
                "user_id_present": False,
                "exception_type": "RuntimeError",
                "error_category": "persistence_error",
            },
        }
    ]
    assert "audit_event_id" not in monitoring_calls[0]["tags"]
    assert "correlation_id" not in monitoring_calls[0]["tags"]
    assert "user_id" not in monitoring_calls[0]["tags"]
    serialized = caplog.text + repr(monitoring_calls)
    for sentinel in sentinels:
        assert sentinel not in serialized


def test_monitoring_failure_is_also_non_fatal(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake = FakeAuditClient(error=RuntimeError("database unavailable"))
    monkeypatch.setattr(audit, "get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr(
        auth_observability,
        "capture_unexpected_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("monitoring down")),
    )

    assert audit.record_authentication_event(
        event_id="00000000-0000-4000-8000-000000001031",
        event_type="logout",
        outcome="failed",
        auth_method="bearer",
        correlation_id="correlation-1031",
        user_id="00000000-0000-4000-8000-000000001032",
        failure_category="service_unavailable",
    ) is False


def test_environment_resolution_failure_is_sanitized_and_non_fatal(
    monkeypatch,
    caplog,
) -> None:
    configure_settings(monkeypatch)
    secret = "Authorization=Bearer must-not-escape"
    monitoring_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        audit,
        "source_environment",
        lambda: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(
        auth_observability,
        "capture_unexpected_message",
        lambda message, level="warning", **tags: monitoring_calls.append(
            {"message": message, "level": level, "tags": tags}
        ),
    )

    with caplog.at_level(logging.WARNING, logger=audit.__name__):
        inserted = audit.record_authentication_event(
            event_id="00000000-0000-4000-8000-000000001031",
            event_type="login",
            outcome="succeeded",
            auth_method="password",
            correlation_id="correlation-1031",
        )

    assert inserted is False
    assert secret not in caplog.text
    assert secret not in repr(monitoring_calls)
    assert monitoring_calls[0]["tags"]["environment"] == "unknown"


def test_idempotency_conflict_warning_is_sanitized_and_non_fatal(
    monkeypatch,
    caplog,
) -> None:
    configure_settings(monkeypatch)

    class ConflictError(RuntimeError):
        code = "23505"

    secret = "different-payload password=must-not-escape"
    fake = FakeAuditClient(error=ConflictError(secret))
    monitoring_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(audit, "get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr(
        auth_observability,
        "capture_unexpected_message",
        lambda message, level="warning", **tags: monitoring_calls.append(
            {"message": message, "level": level, "tags": tags}
        ),
    )

    with caplog.at_level(logging.WARNING, logger=audit.__name__):
        assert audit.record_authentication_event(
            event_id="00000000-0000-4000-8000-000000001031",
            event_type="login",
            outcome="succeeded",
            auth_method="password",
            correlation_id="correlation-1031",
        ) is False

    warning = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.audit.persist.failure"
    )
    assert warning.error_category == "idempotency_conflict"
    assert monitoring_calls[0]["tags"]["error_category"] == "idempotency_conflict"
    assert secret not in caplog.text
    assert secret not in repr(monitoring_calls)


def test_logging_and_monitoring_failures_together_are_non_fatal(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake = FakeAuditClient(error=RuntimeError("database unavailable"))
    monkeypatch.setattr(audit, "get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr(
        audit.logger,
        "warning",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("logger down")),
    )
    monkeypatch.setattr(
        auth_observability,
        "capture_unexpected_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("monitor down")),
    )

    assert audit.record_authentication_event(
        event_id="00000000-0000-4000-8000-000000001031",
        event_type="login",
        outcome="succeeded",
        auth_method="password",
        correlation_id="correlation-1031",
    ) is False
