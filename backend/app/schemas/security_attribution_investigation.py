"""Strict request, RPC, and response models for bounded investigations."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SecurityAttributionEnvironment = Literal[
    "development",
    "staging",
    "production",
]
SecurityAttributionEventCategory = Literal[
    "session_security_change",
    "credential_configuration_read",
    "credential_method_change",
    "credential_recovery",
    "account_assurance_change",
    "account_lifecycle_change",
    "private_security_record_read",
    "access_control_read",
    "access_control_change",
    "private_notification_read",
    "private_security_setting_read",
    "private_security_setting_change",
    "notification_delivery_binding_change",
    "admin_sensitive_read",
    "admin_account_control",
    "admin_moderation_change",
    "admin_content_control",
    "admin_operational_action",
]
SecurityAttributionRouteKey = Literal[
    "auth_logout",
    "auth_account_methods_read",
    "auth_google_link",
    "auth_google_unlink",
    "auth_password_set",
    "auth_password_remove",
    "auth_password_reset_confirm",
    "auth_email_verify",
    "auth_account_delete",
    "field_reports_mine_read",
    "user_blocks_read",
    "user_block_create",
    "user_block_delete",
    "notifications_private_read",
    "notification_preferences_read",
    "notification_preferences_update",
    "push_token_bind",
    "push_token_unbind",
    "admin_self_read",
    "admin_users_read",
    "admin_field_reports_read",
    "admin_stats_read",
    "admin_fields_read",
    "admin_fields_pending_read",
    "admin_field_duplicates_read",
    "admin_games_read",
    "admin_engagement_read",
    "admin_monitoring_read",
    "admin_content_reports_read",
    "admin_notification_candidates_read",
    "admin_user_ban",
    "admin_user_unban",
    "admin_user_suspend",
    "admin_user_unsuspend",
    "admin_field_report_status",
    "admin_field_report_resolve",
    "admin_field_approve",
    "admin_field_reject",
    "admin_field_status",
    "admin_field_update",
    "admin_field_delete",
    "admin_field_status_external",
    "admin_reminders_run",
    "admin_notification_cleanup",
    "admin_game_close",
    "admin_game_extend",
    "admin_game_cancel",
    "admin_content_report_update",
]
SecurityAttributionHttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
SecurityAttributionOutcome = Literal["succeeded", "denied", "failed", "ambiguous"]
SecurityAttributionFailureCategory = Literal[
    "authorization_denied",
    "reauthentication_failed",
    "validation_rejected",
    "conflict",
    "not_found",
    "rate_limited",
    "dependency_unavailable",
    "outcome_unknown",
    "internal_error",
]
SecurityAttributionQueryStatus = Literal["succeeded", "rejected", "failed"]


_OUTCOME_FAILURES: dict[str, frozenset[str | None]] = {
    "succeeded": frozenset({None}),
    "denied": frozenset(
        {"authorization_denied", "reauthentication_failed", "rate_limited"}
    ),
    "failed": frozenset(
        {
            "validation_rejected",
            "conflict",
            "not_found",
            "rate_limited",
            "dependency_unavailable",
            "internal_error",
        }
    ),
    "ambiguous": frozenset({"outcome_unknown"}),
}


def _require_nonzero_uuid(value: object, *, category: str) -> UUID:
    try:
        if isinstance(value, UUID):
            parsed = value
        elif isinstance(value, str):
            parsed = UUID(value)
            if str(parsed) != value:
                raise ValueError
        else:
            raise ValueError
        if parsed.int == 0:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        raise ValueError(f"{category} is invalid") from None
    return parsed


def _require_aware_datetime(value: datetime, *, category: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{category} must include a timezone")
    return value


class SecurityAttributionInvestigationRequest(BaseModel):
    """Only the five database-approved bounded query inputs."""

    model_config = ConfigDict(extra="forbid")

    incident_id: UUID = Field(repr=False)
    environment: SecurityAttributionEnvironment
    window_start: datetime
    window_end: datetime
    limit: int = Field(strict=True, ge=1, le=10_000)

    @field_validator("incident_id", mode="before")
    @classmethod
    def validate_incident_id(cls, value: object) -> UUID:
        return _require_nonzero_uuid(value, category="incident UUID")

    @field_validator("window_start", "window_end")
    @classmethod
    def validate_aware_timestamp(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value, category="investigation timestamp")

    @model_validator(mode="after")
    def validate_window(self) -> "SecurityAttributionInvestigationRequest":
        if self.window_start >= self.window_end:
            raise ValueError("investigation window start must precede end")
        if self.window_end - self.window_start > timedelta(days=31):
            raise ValueError("investigation window exceeds 31 days")
        return self


class SecurityAttributionInvestigationRpcRow(BaseModel):
    """Exact row shape returned by the existing owner-only query RPC."""

    model_config = ConfigDict(extra="forbid")

    query_status: SecurityAttributionQueryStatus
    request_event_id: UUID | None = Field(default=None, repr=False)
    occurred_at: datetime | None = None
    account_pseudonym: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_-]{43}$",
        repr=False,
    )
    pseudonym_epoch: str | None = Field(
        default=None,
        pattern=r"^[0-9]{4}-[0-9]{2}$",
    )
    pseudonym_key_version: int | None = Field(
        default=None,
        strict=True,
        ge=1,
        le=32_767,
    )
    environment: SecurityAttributionEnvironment | None = None
    event_category: SecurityAttributionEventCategory | None = None
    route_key: SecurityAttributionRouteKey | None = None
    http_method: SecurityAttributionHttpMethod | None = None
    outcome: SecurityAttributionOutcome | None = None
    failure_category: SecurityAttributionFailureCategory | None = None
    server_correlation_id: UUID | None = Field(default=None, repr=False)

    @field_validator("request_event_id", "server_correlation_id")
    @classmethod
    def validate_optional_nonzero_uuid(cls, value: UUID | None) -> UUID | None:
        if value is not None and value.int == 0:
            raise ValueError("RPC UUID is invalid")
        return value

    @field_validator("occurred_at")
    @classmethod
    def validate_optional_aware_timestamp(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None:
            _require_aware_datetime(value, category="RPC event timestamp")
        return value

    @model_validator(mode="after")
    def validate_status_shape(self) -> "SecurityAttributionInvestigationRpcRow":
        evidence_values = (
            self.request_event_id,
            self.occurred_at,
            self.account_pseudonym,
            self.pseudonym_epoch,
            self.pseudonym_key_version,
            self.environment,
            self.event_category,
            self.route_key,
            self.http_method,
            self.outcome,
        )
        if self.query_status != "succeeded":
            if any(value is not None for value in evidence_values) or (
                self.failure_category is not None
                or self.server_correlation_id is not None
            ):
                raise ValueError("non-success RPC row contains evidence")
            return self

        if any(value is None for value in evidence_values):
            raise ValueError("successful RPC row is incomplete")
        if self.outcome is None or self.failure_category not in _OUTCOME_FAILURES[
            self.outcome
        ]:
            raise ValueError("RPC outcome and failure category are inconsistent")
        return self


class SecurityAttributionEvidenceRow(BaseModel):
    """Least-disclosure public evidence row; no raw identity or event row ID."""

    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    account_pseudonym: str = Field(
        pattern=r"^[A-Za-z0-9_-]{43}$",
        repr=False,
    )
    pseudonym_epoch: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    pseudonym_key_version: int = Field(strict=True, ge=1, le=32_767)
    environment: SecurityAttributionEnvironment
    event_category: SecurityAttributionEventCategory
    route_key: SecurityAttributionRouteKey
    http_method: SecurityAttributionHttpMethod
    outcome: SecurityAttributionOutcome
    failure_category: SecurityAttributionFailureCategory | None = None
    server_correlation_id: UUID | None = Field(default=None, repr=False)

    @classmethod
    def from_rpc_row(
        cls,
        row: SecurityAttributionInvestigationRpcRow,
    ) -> "SecurityAttributionEvidenceRow":
        return cls(
            occurred_at=row.occurred_at,
            account_pseudonym=row.account_pseudonym,
            pseudonym_epoch=row.pseudonym_epoch,
            pseudonym_key_version=row.pseudonym_key_version,
            environment=row.environment,
            event_category=row.event_category,
            route_key=row.route_key,
            http_method=row.http_method,
            outcome=row.outcome,
            failure_category=row.failure_category,
            server_correlation_id=row.server_correlation_id,
        )


class SecurityAttributionInvestigationResponse(BaseModel):
    """Bounded case/window metadata plus approved pseudonymous evidence."""

    model_config = ConfigDict(extra="forbid")

    incident_id: UUID = Field(repr=False)
    environment: SecurityAttributionEnvironment
    window_start: datetime
    window_end: datetime
    result_count: int = Field(strict=True, ge=0, le=10_000)
    evidence: list[SecurityAttributionEvidenceRow] = Field(repr=False)

    @model_validator(mode="after")
    def validate_result_count(self) -> "SecurityAttributionInvestigationResponse":
        if self.result_count != len(self.evidence):
            raise ValueError("investigation result count is inconsistent")
        return self
