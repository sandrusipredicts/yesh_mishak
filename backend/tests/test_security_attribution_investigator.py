from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import admin
from app.auth import dependencies as auth_dependencies
from app.auth.dependencies import (
    require_admin,
    require_security_attribution_investigator,
)
from app.auth.jwt import create_access_token
from app.core.config import Settings, get_settings
from app.main import app
from app.services import security_attribution_investigation as investigation
from app.services.security_attribution_investigation_config import (
    ActiveSecurityAttributionInvestigationConfiguration,
    SecurityAttributionInvestigationConfiguration,
    SecurityAttributionInvestigationConfigurationError,
    SecurityAttributionInvestigatorPrincipal,
    load_security_attribution_investigation_configuration,
)


INVESTIGATOR_ID = UUID("00000000-0000-4000-8000-000000000401")
OTHER_ADMIN_ID = UUID("00000000-0000-4000-8000-000000000402")
USER_ID = UUID("00000000-0000-4000-8000-000000000403")
INCIDENT_ID = UUID("00000000-0000-4000-8000-000000001031")
EVENT_ID = UUID("00000000-0000-4000-8000-000000001032")
CORRELATION_ID = UUID("00000000-0000-4000-8000-000000001033")
ACCOUNT_UUID_SENTINEL = "00000000-0000-4000-8000-000000009999"
WINDOW_START = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 7, 2, 0, 0, tzinfo=timezone.utc)
PSEUDONYM = "A" * 43
ENDPOINT = "/admin/security-attribution/investigate"


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeUsersQuery:
    def __init__(self, users: dict[str, dict[str, Any]]) -> None:
        self.users = users
        self.user_id: str | None = None

    def select(self, _columns: str) -> "FakeUsersQuery":
        return self

    def eq(self, column: str, value: str) -> "FakeUsersQuery":
        assert column == "id"
        self.user_id = value
        return self

    def limit(self, value: int) -> "FakeUsersQuery":
        assert value == 1
        return self

    def execute(self) -> FakeResponse:
        user = self.users.get(self.user_id or "")
        return FakeResponse(data=[dict(user)] if user is not None else [])


class FakeAuthClient:
    def __init__(self, users: list[dict[str, Any]]) -> None:
        self.users = {str(user["id"]): user for user in users}
        self.table_calls: list[str] = []

    def table(self, name: str) -> FakeUsersQuery:
        self.table_calls.append(name)
        assert name == "users"
        return FakeUsersQuery(self.users)


class FakeGateway:
    def __init__(
        self,
        response: investigation.AuditedSecurityAttributionRpcResponse | None = None,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.response = response or investigation.AuditedSecurityAttributionRpcResponse(
            rows=[],
            access_audit_persisted=True,
        )
        self.error = error
        self.calls: list[
            investigation.BoundedSecurityAttributionInvestigationQuery
        ] = []

    def query_audited_security_attribution(
        self,
        query: investigation.BoundedSecurityAttributionInvestigationQuery,
    ) -> investigation.AuditedSecurityAttributionRpcResponse:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return self.response


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_KEY": "public-test-key",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
        "GOOGLE_CLIENT_ID": "google-test-client",
        "JWT_SECRET": "jwt-test-secret-with-at-least-32-bytes",
        "SECURITY_ATTRIBUTION_INVESTIGATION_ENABLED": True,
        "SECURITY_ATTRIBUTION_INVESTIGATOR_PRINCIPALS": str(INVESTIGATOR_ID),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def active_configuration(
    *principal_ids: UUID,
) -> SecurityAttributionInvestigationConfiguration:
    return SecurityAttributionInvestigationConfiguration(
        enabled=True,
        active=ActiveSecurityAttributionInvestigationConfiguration(
            investigator_principals=frozenset(principal_ids),
        ),
    )


def principal(
    principal_id: UUID = INVESTIGATOR_ID,
) -> SecurityAttributionInvestigatorPrincipal:
    return SecurityAttributionInvestigatorPrincipal(internal_id=principal_id)


def user(principal_id: UUID, *, role: str) -> dict[str, Any]:
    return {
        "id": str(principal_id),
        "email": f"{role}@example.invalid",
        "name": role.title(),
        "role": role,
        "status": "active",
        "tokens_valid_after": None,
    }


def valid_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "incident_id": str(INCIDENT_ID),
        "environment": "development",
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "limit": 100,
    }
    body.update(overrides)
    return body


def rpc_evidence_row(
    *,
    occurred_at: datetime = WINDOW_START + timedelta(hours=1),
    pseudonym: str = PSEUDONYM,
    **overrides: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "query_status": "succeeded",
        "request_event_id": str(EVENT_ID),
        "occurred_at": occurred_at.isoformat(),
        "account_pseudonym": pseudonym,
        "pseudonym_epoch": "2026-07",
        "pseudonym_key_version": 1,
        "environment": "development",
        "event_category": "session_security_change",
        "route_key": "auth_logout",
        "http_method": "POST",
        "outcome": "succeeded",
        "failure_category": None,
        "server_correlation_id": str(CORRELATION_ID),
    }
    row.update(overrides)
    return row


def status_only_rpc_row(status: str) -> dict[str, object]:
    return {
        "query_status": status,
        "request_event_id": None,
        "occurred_at": None,
        "account_pseudonym": None,
        "pseudonym_epoch": None,
        "pseudonym_key_version": None,
        "environment": None,
        "event_category": None,
        "route_key": None,
        "http_method": None,
        "outcome": None,
        "failure_category": None,
        "server_correlation_id": None,
    }


def authorize_with_real_token(
    monkeypatch: pytest.MonkeyPatch,
    current_user: dict[str, Any],
    *,
    configuration: SecurityAttributionInvestigationConfiguration,
) -> dict[str, str]:
    fake_client = FakeAuthClient([current_user])
    monkeypatch.setattr(
        auth_dependencies,
        "get_supabase_service_role_client",
        lambda: fake_client,
    )
    monkeypatch.setattr(
        auth_dependencies,
        "get_security_attribution_investigation_configuration",
        lambda: configuration,
    )
    return {
        "Authorization": (
            "Bearer "
            + create_access_token(
                subject=str(current_user["id"]),
                email=str(current_user["email"]),
            )
        )
    }


@pytest.fixture(autouse=True)
def isolate_investigator_dependencies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.middleware.request_metrics.record_api_request_metric",
        lambda **_kwargs: None,
    )
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(require_security_attribution_investigator, None)
    app.dependency_overrides.pop(
        investigation.get_security_attribution_investigation_gateway,
        None,
    )
    yield
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(require_security_attribution_investigator, None)
    app.dependency_overrides.pop(
        investigation.get_security_attribution_investigation_gateway,
        None,
    )


def test_investigation_capability_is_disabled_by_default() -> None:
    configuration = load_security_attribution_investigation_configuration(
        make_settings(
            SECURITY_ATTRIBUTION_INVESTIGATION_ENABLED=False,
            SECURITY_ATTRIBUTION_INVESTIGATOR_PRINCIPALS=None,
        )
    )

    assert configuration.enabled is False
    assert configuration.active is None


def test_enabled_configuration_loads_one_explicit_principal() -> None:
    configuration = load_security_attribution_investigation_configuration(
        make_settings()
    )

    assert configuration.enabled is True
    assert configuration.active is not None
    assert configuration.active.authorizes(principal()) is True
    assert configuration.active.authorizes(principal(OTHER_ADMIN_ID)) is False


@pytest.mark.parametrize(
    "configured_value",
    [
        None,
        "",
        "not-a-uuid",
        "00000000-0000-0000-0000-000000000000",
        "ABCDEFAB-0000-4000-8000-000000000401",
        f"{INVESTIGATOR_ID}, {OTHER_ADMIN_ID}",
        f"{INVESTIGATOR_ID},{INVESTIGATOR_ID}",
        f"{INVESTIGATOR_ID},",
    ],
)
def test_enabled_invalid_principal_configuration_fails_closed(
    configured_value: str | None,
) -> None:
    with pytest.raises(
        SecurityAttributionInvestigationConfigurationError,
        match=r"^security attribution investigation configuration is invalid$",
    ):
        load_security_attribution_investigation_configuration(
            make_settings(
                SECURITY_ATTRIBUTION_INVESTIGATOR_PRINCIPALS=configured_value
            )
        )


def test_investigator_identity_is_redacted_from_repr_and_errors() -> None:
    configured_value = f"{INVESTIGATOR_ID},{OTHER_ADMIN_ID}"
    settings = make_settings(
        SECURITY_ATTRIBUTION_INVESTIGATOR_PRINCIPALS=configured_value
    )
    configuration = load_security_attribution_investigation_configuration(settings)

    diagnostics = " ".join(
        (repr(settings), repr(configuration), repr(configuration.active), repr(principal()))
    )
    assert "[REDACTED]" in diagnostics
    assert str(INVESTIGATOR_ID) not in diagnostics
    assert str(OTHER_ADMIN_ID) not in diagnostics

    duplicate_value = f"{INVESTIGATOR_ID},{INVESTIGATOR_ID}"
    with pytest.raises(SecurityAttributionInvestigationConfigurationError) as exc_info:
        load_security_attribution_investigation_configuration(
            make_settings(
                SECURITY_ATTRIBUTION_INVESTIGATOR_PRINCIPALS=duplicate_value
            )
        )
    assert duplicate_value not in f"{exc_info.value!s} {exc_info.value!r}"


@pytest.mark.parametrize("value", ["1", "yes", "TRUE", 1, None])
def test_investigation_enabled_setting_is_strict(value: object) -> None:
    with pytest.raises(ValidationError):
        make_settings(SECURITY_ATTRIBUTION_INVESTIGATION_ENABLED=value)


def test_unauthenticated_request_is_denied_without_evidence() -> None:
    response = TestClient(app).post(ENDPOINT, json=valid_body())

    assert response.status_code == 401
    serialized = response.text.lower()
    assert "evidence" not in serialized
    assert "result_count" not in serialized


def test_normal_authenticated_user_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    current_user = user(USER_ID, role="user")
    headers = authorize_with_real_token(
        monkeypatch,
        current_user,
        configuration=active_configuration(INVESTIGATOR_ID),
    )

    response = TestClient(app).post(ENDPOINT, json=valid_body(), headers=headers)

    assert response.status_code == 403
    assert "evidence" not in response.text.lower()


def test_ordinary_admin_without_capability_is_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = user(OTHER_ADMIN_ID, role="admin")
    headers = authorize_with_real_token(
        monkeypatch,
        current_user,
        configuration=active_configuration(INVESTIGATOR_ID),
    )

    response = TestClient(app).post(ENDPOINT, json=valid_body(), headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    assert "result_count" not in response.text


def test_disabled_capability_denies_an_allowlisted_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = user(INVESTIGATOR_ID, role="admin")
    headers = authorize_with_real_token(
        monkeypatch,
        current_user,
        configuration=SecurityAttributionInvestigationConfiguration(
            enabled=False,
            active=None,
        ),
    )

    response = TestClient(app).post(ENDPOINT, json=valid_body(), headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_request_controlled_identity_cannot_grant_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = user(OTHER_ADMIN_ID, role="admin")
    headers = authorize_with_real_token(
        monkeypatch,
        current_user,
        configuration=active_configuration(INVESTIGATOR_ID),
    )
    fake_gateway = FakeGateway()
    app.dependency_overrides[
        investigation.get_security_attribution_investigation_gateway
    ] = lambda: fake_gateway

    response = TestClient(app).post(
        ENDPOINT,
        json=valid_body(investigator_principal=str(INVESTIGATOR_ID)),
        headers=headers,
    )

    assert response.status_code in {403, 422}
    assert fake_gateway.calls == []


def _override_authorized_investigator(fake_gateway: FakeGateway) -> None:
    app.dependency_overrides[require_security_attribution_investigator] = principal
    app.dependency_overrides[
        investigation.get_security_attribution_investigation_gateway
    ] = lambda: fake_gateway


@pytest.mark.parametrize(
    "body_update",
    [
        {"incident_id": "not-a-uuid"},
        {"incident_id": "00000000-0000-0000-0000-000000000000"},
        {"environment": "preview"},
        {"window_start": "2026-07-01T00:00:00"},
        {"window_end": "2026-07-02T00:00:00"},
        {"window_end": WINDOW_START.isoformat()},
        {"window_end": (WINDOW_START + timedelta(days=31, seconds=1)).isoformat()},
        {"limit": 0},
        {"limit": -1},
        {"limit": 10_001},
        {"limit": 1.5},
        {"sort": "occurred_at desc"},
        {"account_uuid": ACCOUNT_UUID_SENTINEL},
        {"email": "investigator@example.invalid"},
        {"account_pseudonym": PSEUDONYM},
        {"sql": "select 1"},
    ],
)
def test_invalid_or_unapproved_request_fields_are_rejected_before_gateway(
    body_update: dict[str, object],
) -> None:
    fake_gateway = FakeGateway()
    _override_authorized_investigator(fake_gateway)

    response = TestClient(app).post(
        ENDPOINT,
        json=valid_body(**body_update),
    )

    assert response.status_code == 422
    assert fake_gateway.calls == []
    serialized = response.text
    assert ACCOUNT_UUID_SENTINEL not in serialized
    assert PSEUDONYM not in serialized


def test_authorized_investigator_sends_only_exact_bounded_rpc_parameters() -> None:
    fake_gateway = FakeGateway()
    _override_authorized_investigator(fake_gateway)

    response = TestClient(app).post(ENDPOINT, json=valid_body())

    assert response.status_code == 200
    assert len(fake_gateway.calls) == 1
    query = fake_gateway.calls[0]
    assert query.capability == "security_attribution_investigate"
    assert query.rpc_name == "query_security_request_attribution_events"
    assert query.rpc_parameters == {
        "p_incident_id": str(INCIDENT_ID),
        "p_environment": "development",
        "p_window_start": WINDOW_START.isoformat(),
        "p_window_end": WINDOW_END.isoformat(),
        "p_result_limit": 100,
    }
    assert set(query.rpc_parameters).isdisjoint(
        {
            "account_uuid",
            "email",
            "username",
            "phone",
            "account_pseudonym",
            "sql",
            "investigator_principal",
        }
    )
    assert "table" not in dir(fake_gateway)


def test_success_response_requires_persisted_access_audit_and_is_least_disclosure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_gateway = FakeGateway(
        investigation.AuditedSecurityAttributionRpcResponse(
            rows=[rpc_evidence_row()],
            access_audit_persisted=True,
        )
    )
    _override_authorized_investigator(fake_gateway)

    with caplog.at_level(logging.INFO, logger=admin.__name__):
        response = TestClient(app).post(ENDPOINT, json=valid_body())

    assert response.status_code == 200
    payload = response.json()
    assert payload["incident_id"] == str(INCIDENT_ID)
    assert payload["result_count"] == 1
    assert payload["evidence"] == [
        {
            "occurred_at": "2026-07-01T01:00:00Z",
            "account_pseudonym": PSEUDONYM,
            "pseudonym_epoch": "2026-07",
            "pseudonym_key_version": 1,
            "environment": "development",
            "event_category": "session_security_change",
            "route_key": "auth_logout",
            "http_method": "POST",
            "outcome": "succeeded",
            "failure_category": None,
            "server_correlation_id": str(CORRELATION_ID),
        }
    ]
    serialized = response.text.lower()
    for forbidden in (
        "request_event_id",
        ACCOUNT_UUID_SENTINEL,
        "email",
        "username",
        "phone",
        "token",
        "user_agent",
        "authorization",
        "sql",
        "hmac",
    ):
        assert forbidden.lower() not in serialized

    success_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "security_attribution.investigation"
        and record.levelno == logging.INFO
    ]
    assert len(success_records) == 1
    assert success_records[0].result_count == 1
    diagnostics = repr(success_records[0].__dict__)
    assert PSEUDONYM not in diagnostics
    assert str(INVESTIGATOR_ID) not in diagnostics


def test_zero_result_success_is_valid_after_audit_persistence() -> None:
    fake_gateway = FakeGateway(
        investigation.AuditedSecurityAttributionRpcResponse(
            rows=[],
            access_audit_persisted=True,
        )
    )
    _override_authorized_investigator(fake_gateway)

    response = TestClient(app).post(ENDPOINT, json=valid_body())

    assert response.status_code == 200
    assert response.json()["result_count"] == 0
    assert response.json()["evidence"] == []


def test_rpc_order_is_preserved_without_application_sorting() -> None:
    first = rpc_evidence_row(
        occurred_at=WINDOW_START + timedelta(hours=1),
        pseudonym="A" * 43,
    )
    second = rpc_evidence_row(
        occurred_at=WINDOW_START + timedelta(hours=2),
        pseudonym="B" * 43,
        request_event_id="00000000-0000-4000-8000-000000001034",
    )
    fake_gateway = FakeGateway(
        investigation.AuditedSecurityAttributionRpcResponse(
            rows=[first, second],
            access_audit_persisted=True,
        )
    )
    _override_authorized_investigator(fake_gateway)

    response = TestClient(app).post(ENDPOINT, json=valid_body())

    assert response.status_code == 200
    assert [row["account_pseudonym"] for row in response.json()["evidence"]] == [
        "A" * 43,
        "B" * 43,
    ]


@pytest.mark.parametrize(
    "rows",
    [
        {"not": "a-list"},
        [rpc_evidence_row(extra_column="not-approved")],
        [rpc_evidence_row(pseudonym="short")],
        [rpc_evidence_row(environment="production")],
        [rpc_evidence_row(occurred_at=WINDOW_END)],
        [
            rpc_evidence_row(occurred_at=WINDOW_START + timedelta(hours=2)),
            rpc_evidence_row(
                occurred_at=WINDOW_START + timedelta(hours=1),
                request_event_id="00000000-0000-4000-8000-000000001034",
            ),
        ],
        [status_only_rpc_row("rejected"), rpc_evidence_row()],
    ],
)
def test_unexpected_rpc_shape_returns_no_evidence(rows: object) -> None:
    fake_gateway = FakeGateway(
        investigation.AuditedSecurityAttributionRpcResponse(
            rows=rows,
            access_audit_persisted=True,
        )
    )
    _override_authorized_investigator(fake_gateway)

    response = TestClient(app).post(ENDPOINT, json=valid_body())

    assert response.status_code == 503
    assert response.json()["code"] == "SECURITY_ATTRIBUTION_INVESTIGATION_UNAVAILABLE"
    assert "evidence" not in response.text.lower()
    assert PSEUDONYM not in response.text


def test_query_failure_with_persisted_failure_audit_returns_no_evidence(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_gateway = FakeGateway(
        investigation.AuditedSecurityAttributionRpcResponse(
            rows=[status_only_rpc_row("failed")],
            access_audit_persisted=True,
        )
    )
    _override_authorized_investigator(fake_gateway)

    with caplog.at_level(logging.WARNING, logger=admin.__name__):
        response = TestClient(app).post(ENDPOINT, json=valid_body())

    assert response.status_code == 503
    assert "evidence" not in response.text.lower()
    warning = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "security_attribution.investigation"
    )
    assert warning.failure_category == "query_failed"
    assert warning.result_count == 0


def test_rpc_rejection_with_persisted_rejection_audit_is_bounded() -> None:
    fake_gateway = FakeGateway(
        investigation.AuditedSecurityAttributionRpcResponse(
            rows=[status_only_rpc_row("rejected")],
            access_audit_persisted=True,
        )
    )
    _override_authorized_investigator(fake_gateway)

    response = TestClient(app).post(ENDPOINT, json=valid_body())

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "evidence" not in response.text.lower()


def test_access_audit_failure_returns_no_evidence_even_when_rows_exist(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_gateway = FakeGateway(
        investigation.AuditedSecurityAttributionRpcResponse(
            rows=[rpc_evidence_row()],
            access_audit_persisted=False,
        )
    )
    _override_authorized_investigator(fake_gateway)

    with caplog.at_level(logging.WARNING, logger=admin.__name__):
        response = TestClient(app).post(ENDPOINT, json=valid_body())

    assert response.status_code == 503
    assert "evidence" not in response.text.lower()
    assert PSEUDONYM not in response.text
    warning = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "security_attribution.investigation"
    )
    assert warning.failure_category == "access_audit_failed"
    assert warning.result_count == 0


def test_raw_gateway_exception_is_not_returned_logged_or_monitored(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    exception_secret = (
        "email=secret@example.invalid token=secret-token "
        f"account={ACCOUNT_UUID_SENTINEL} pseudonym={PSEUDONYM}"
    )
    fake_gateway = FakeGateway(error=RuntimeError(exception_secret))
    monitoring: list[dict[str, Any]] = []
    monkeypatch.setattr(
        admin,
        "safe_auth_monitor",
        lambda message, level="warning", **tags: monitoring.append(
            {"message": message, "level": level, "tags": tags}
        ),
    )
    _override_authorized_investigator(fake_gateway)

    with caplog.at_level(logging.WARNING, logger=admin.__name__):
        response = TestClient(app).post(ENDPOINT, json=valid_body())

    assert response.status_code == 503
    diagnostics = (
        response.text
        + repr([record.__dict__ for record in caplog.records])
        + repr(monitoring)
    )
    for forbidden in (
        exception_secret,
        "secret@example.invalid",
        "secret-token",
        ACCOUNT_UUID_SENTINEL,
        PSEUDONYM,
        str(INVESTIGATOR_ID),
    ):
        assert forbidden not in diagnostics
    assert monitoring[0]["message"] == "Security attribution investigation failed"
    assert set(monitoring[0]["tags"]) == {
        "event",
        "route_key",
        "environment",
        "request_id",
        "failure_category",
        "result_count",
    }
    assert monitoring[0]["tags"]["failure_category"] == "unexpected_failure"


def test_default_runtime_gateway_is_unavailable_and_never_returns_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = user(INVESTIGATOR_ID, role="admin")
    headers = authorize_with_real_token(
        monkeypatch,
        current_user,
        configuration=active_configuration(INVESTIGATOR_ID),
    )

    response = TestClient(app).post(ENDPOINT, json=valid_body(), headers=headers)

    assert response.status_code == 503
    assert response.json()["code"] == "SECURITY_ATTRIBUTION_INVESTIGATION_UNAVAILABLE"
    assert "evidence" not in response.text.lower()
    assert PSEUDONYM not in response.text


def test_query_and_audit_wrapper_reprs_hide_principal_and_evidence() -> None:
    request = admin.SecurityAttributionInvestigationRequest.model_validate(valid_body())
    query = investigation.BoundedSecurityAttributionInvestigationQuery(
        request=request,
        investigator_principal=principal(),
    )
    response = investigation.AuditedSecurityAttributionRpcResponse(
        rows=[rpc_evidence_row()],
        access_audit_persisted=True,
    )

    diagnostics = f"{query!r} {response!r}"
    assert "[REDACTED]" in diagnostics
    assert str(INVESTIGATOR_ID) not in diagnostics
    assert str(INCIDENT_ID) not in diagnostics
    assert PSEUDONYM not in diagnostics


def test_no_application_database_adapter_or_direct_table_api_is_exposed() -> None:
    gateway = investigation.get_security_attribution_investigation_gateway()

    assert isinstance(
        gateway,
        investigation.UnavailableSecurityAttributionInvestigationGateway,
    )
    assert not hasattr(gateway, "table")
    assert not hasattr(gateway, "rpc")
    assert not hasattr(gateway, "service_role_client")
