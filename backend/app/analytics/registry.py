"""E09-02: declarative registry for first-party analytics events.

The registry is the single contract for what the ingestion pipeline accepts.
Every event name and every property must be declared here with a bounded set
of allowed values; anything else is rejected before it can reach the
database. Future issues add events by extending EVENT_REGISTRY (and the
matching CHECK constraints in backend/migrations/analytics_events.sql plus
the client mirror in frontend/src/analytics/registry.js).

Privacy envelope (owner decision D1): events are strictly anonymous. The
registry must never declare properties that could carry user IDs, resource
IDs, URLs, coordinates, or free text -- only closed enums of coarse values.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping

SCREEN_NAMES: frozenset[str] = frozenset(
    {
        "map",
        "game_details",
        "profile",
        "notifications",
        "admin",
    }
)


@dataclass(frozen=True)
class PropertySpec:
    """A single allowed event property with a closed set of values."""

    allowed_values: frozenset[str] = field(default_factory=frozenset)
    required: bool = True


# Seed events approved in owner decision D2. Property values must always be
# closed enums -- never free text.
EVENT_REGISTRY: dict[str, dict[str, PropertySpec]] = {
    "app_open": {},
    "screen_view": {
        "screen": PropertySpec(allowed_values=SCREEN_NAMES, required=True),
    },
}


def is_registered_event(event_name: str) -> bool:
    return event_name in EVENT_REGISTRY


def validate_event(event_name: str, properties: Mapping[str, Any]) -> list[str]:
    """Validate an event against the registry.

    Returns a list of human-readable validation errors; an empty list means
    the event conforms to the registry contract.
    """
    if not is_registered_event(event_name):
        return [f"unknown event_name: {event_name!r}"]

    errors: list[str] = []
    spec = EVENT_REGISTRY[event_name]

    for property_name in properties:
        if property_name not in spec:
            errors.append(
                f"unknown property {property_name!r} for event {event_name!r}"
            )

    for property_name, property_spec in spec.items():
        if property_name not in properties:
            if property_spec.required:
                errors.append(
                    f"missing required property {property_name!r} for event {event_name!r}"
                )
            continue

        value = properties[property_name]
        if not isinstance(value, str):
            errors.append(
                f"property {property_name!r} for event {event_name!r} must be a string"
            )
            continue
        if value not in property_spec.allowed_values:
            errors.append(
                f"invalid value for property {property_name!r} of event {event_name!r}"
            )

    return errors
