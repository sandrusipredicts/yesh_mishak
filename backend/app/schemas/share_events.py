from typing import Literal

from pydantic import BaseModel, Field, model_validator


ShareEventName = Literal["share_action", "link_open"]
EntityType = Literal["game", "field"]
Platform = Literal["web", "android", "ios"]
Mechanism = Literal["native_share", "copy_link"]
ShareOutcome = Literal["shared", "copied", "cancelled", "unavailable", "failed"]
LinkOpenOutcome = Literal["valid", "invalid", "not_found", "deferred_for_auth"]
ErrorCategory = Literal[
    "invalid_resource",
    "unsupported_platform",
    "share_unavailable",
    "share_failed",
    "clipboard_failed",
    "malformed_link",
    "unsupported_link",
    "resource_not_found",
    "resolution_failed",
]


class ShareEventCreate(BaseModel):
    event_name: ShareEventName
    entity_type: EntityType
    platform: Platform
    mechanism: Mechanism | None = None
    outcome: ShareOutcome | LinkOpenOutcome
    error_category: ErrorCategory | None = Field(default=None)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_event_contract(self) -> "ShareEventCreate":
        if self.event_name == "share_action":
            if self.mechanism is None:
                raise ValueError("share_action requires mechanism")
            if self.outcome not in ("shared", "copied", "cancelled", "unavailable", "failed"):
                raise ValueError("invalid share_action outcome")
            return self

        if self.mechanism is not None:
            raise ValueError("link_open does not accept mechanism")
        if self.outcome not in ("valid", "invalid", "not_found", "deferred_for_auth"):
            raise ValueError("invalid link_open outcome")
        return self
