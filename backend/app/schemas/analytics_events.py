from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.analytics.registry import validate_event

Platform = Literal["web", "android", "ios"]

MAX_BATCH_SIZE = 20
MAX_EVENT_NAME_LENGTH = 64
MAX_APP_VERSION_LENGTH = 32

# Client-supplied timestamps outside this window are discarded so the
# server-side default (recorded_at = now()) wins. Keeps clock-skewed or
# replayed clients from polluting the daily aggregation.
CLIENT_TIMESTAMP_MAX_PAST = timedelta(hours=24)
CLIENT_TIMESTAMP_MAX_FUTURE = timedelta(minutes=5)


class AnalyticsEventIn(BaseModel):
    event_name: str = Field(min_length=1, max_length=MAX_EVENT_NAME_LENGTH)
    platform: Platform
    app_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_APP_VERSION_LENGTH,
        pattern=r"^[0-9A-Za-z.+\-]+$",
    )
    occurred_at: datetime | None = None
    properties: dict[str, str] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_event_contract(self) -> "AnalyticsEventIn":
        errors = validate_event(self.event_name, self.properties)
        if errors:
            raise ValueError("; ".join(errors))

        self.occurred_at = _clamp_client_timestamp(self.occurred_at)
        return self


class AnalyticsEventBatch(BaseModel):
    # Items are validated individually by the router so one malformed event
    # rejects that item, not the whole batch (partial acceptance).
    events: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_BATCH_SIZE)

    model_config = {"extra": "forbid"}


def _clamp_client_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if value < now - CLIENT_TIMESTAMP_MAX_PAST:
        return None
    if value > now + CLIENT_TIMESTAMP_MAX_FUTURE:
        return None
    return value
