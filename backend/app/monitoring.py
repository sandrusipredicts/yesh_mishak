"""Centralized Sentry monitoring wiring for the FastAPI backend.

This is the only module that imports sentry_sdk directly outside of the two
call sites in app/main.py's exception handlers (which call the thin
capture_unexpected_exception wrapper below, not sentry_sdk itself) -- so
Sentry usage never scatters across unrelated route/service modules.

Design mirrors frontend/src/monitoring/ (E09-01): pure environment/release
resolution functions that are unit-testable without the SDK, a fail-safe
init that can never raise, and a single explicit choke point for redaction.
"""
import logging
import re
from typing import Any, Optional
from urllib.parse import urlsplit

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.core.config import Settings

logger = logging.getLogger("app.monitoring")

LOCAL_ENVIRONMENT = "local"
UNKNOWN_RELEASE = "unknown"
MAX_REDACT_DEPTH = 8
PRODUCTION_TRACE_SAMPLE_RATE = 0.05
DEVELOPMENT_TRACE_SAMPLE_RATE = 1.0

_TRACE_ROUTE_GROUPS = (
    ("/auth", "authentication"),
    ("/fields", "fields-map"),
    ("/field-reports", "fields-map"),
    ("/games", "games"),
    ("/notifications", "notifications"),
    ("/analytics/events", "analytics-ingestion"),
)

# Same conservative, case-insensitive substring policy as the frontend
# redaction module: false positives (over-redacting) are preferred over
# false negatives (leaking a secret).
_SENSITIVE_KEY_PATTERN = re.compile(
    r"pass(word)?|token|secret|authoriz|cookie|api[-_]?key|credential|jwt|"
    r"refresh|verification|dsn|push[-_]?token",
    re.IGNORECASE,
)
_COORDINATE_KEY_PATTERN = re.compile(
    r"^(lat(itude)?|lon(gitude)?|lng|coords?|coordinates?)$", re.IGNORECASE
)
_COMMAND_LINE_KEY_PATTERN = re.compile(
    r"^(?:(?:sys|process)[._-])?argv$|"
    r"^command[._-]?line(?:[._-]?(?:args?|arguments?))?$",
    re.IGNORECASE,
)

_enabled = False


def resolve_environment(explicit_environment: Optional[str]) -> str:
    """Deployment-driven, not guessed: Railway/CI must set SENTRY_ENVIRONMENT
    explicitly for anything beyond local development. Absent that, this
    defaults to 'local' -- never 'production' -- so a misconfigured deploy
    can never silently contaminate production issue statistics."""
    if explicit_environment and explicit_environment.strip():
        return explicit_environment.strip()
    return LOCAL_ENVIRONMENT


def resolve_release(explicit_release: Optional[str]) -> str:
    """The release string is computed by CI/deployment and injected via
    SENTRY_RELEASE. The backend never fabricates a version itself."""
    if explicit_release and explicit_release.strip():
        return explicit_release.strip()
    return UNKNOWN_RELEASE


def trace_sample_rate(environment: str) -> float:
    """Environment-aware APM sampling with no local or preview telemetry."""
    if environment == "production":
        return PRODUCTION_TRACE_SAMPLE_RATE
    if environment == "development":
        return DEVELOPMENT_TRACE_SAMPLE_RATE
    return 0.0


def normalize_transaction_path(path: Optional[str]) -> Optional[str]:
    """Map supported API paths to five bounded, privacy-safe route groups."""
    if not isinstance(path, str):
        return None
    # SDK-created transaction names can be either a raw path or
    # ``METHOD /path``.  Supporting both keeps one-off verification and
    # framework-generated transactions on the same allowlist.
    if " " in path:
        possible_method, possible_path = path.split(" ", 1)
        if possible_method.isalpha() and possible_path.startswith("/"):
            path = possible_path
    safe_path = urlsplit(path).path if "://" in path else _safe_url_path(path)
    for prefix, group in _TRACE_ROUTE_GROUPS:
        if safe_path == prefix or safe_path.startswith(f"{prefix}/"):
            return group
    return None


def before_send_transaction(event: dict, hint: dict) -> Optional[dict]:
    """Keep only approved route groups and replace raw paths with stable names."""
    request = event.get("request")
    request_url = request.get("url") if isinstance(request, dict) else None
    transaction = event.get("transaction")
    candidate = request_url or transaction
    group = normalize_transaction_path(candidate)
    if group is None:
        return None

    method = "REQUEST"
    if isinstance(request, dict) and isinstance(request.get("method"), str):
        method = request["method"].upper()
    event["transaction"] = f"{method} {group}"
    if isinstance(request, dict):
        # Raw route URLs may contain field/game identifiers.  The normalized
        # group is sufficient for latency operations and contains no IDs.
        request["url"] = f"/{group}"
    return redact_event(event, hint)


def is_monitoring_enabled(
    dsn: Optional[str], environment: str, local_override_enabled: Optional[bool]
) -> bool:
    """Enabled automatically in any non-local deployed environment that has
    a DSN configured; disabled by default for local development unless
    explicitly overridden (SENTRY_ENABLED=true) for integration testing."""
    if not dsn or not dsn.strip():
        return False
    if environment == LOCAL_ENVIRONMENT:
        return bool(local_override_enabled)
    return True


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    return bool(_SENSITIVE_KEY_PATTERN.search(key) or _COORDINATE_KEY_PATTERN.match(key))


def redact_deep(value: Any, *, depth: int = 0, seen: Optional[set] = None) -> Any:
    """Deep-redacts an arbitrary value without mutating the input. Guards
    against circular references and excessive nesting."""
    if seen is None:
        seen = set()

    if value is None or depth >= MAX_REDACT_DEPTH:
        return value if value is None else "[MaxDepth]"

    if isinstance(value, (list, tuple)):
        return [redact_deep(item, depth=depth + 1, seen=seen) for item in value]

    if isinstance(value, dict):
        obj_id = id(value)
        if obj_id in seen:
            return "[Circular]"
        seen = seen | {obj_id}
        result = {}
        for key, val in value.items():
            if _is_sensitive_key(key):
                continue
            elif isinstance(val, (dict, list, tuple)):
                result[key] = redact_deep(val, depth=depth + 1, seen=seen)
            else:
                result[key] = val
        return result

    return value


def remove_command_line_arguments(
    value: Any, *, depth: int = 0, seen: Optional[set] = None
) -> Any:
    """Remove SDK/runtime command-line argument fields at any nesting level.

    Matching is deliberately narrow so exception values, stack frames, tags,
    fingerprints, and ordinary application fields named ``args`` remain
    available for grouping and debugging.
    """
    if seen is None:
        seen = set()

    if value is None or depth >= MAX_REDACT_DEPTH:
        return value

    if isinstance(value, dict):
        obj_id = id(value)
        if obj_id in seen:
            return "[Circular]"
        seen = seen | {obj_id}
        return {
            key: remove_command_line_arguments(val, depth=depth + 1, seen=seen)
            if isinstance(val, (dict, list, tuple))
            else val
            for key, val in value.items()
            if not (isinstance(key, str) and _COMMAND_LINE_KEY_PATTERN.match(key))
        }

    if isinstance(value, (list, tuple)):
        return [
            remove_command_line_arguments(item, depth=depth + 1, seen=seen)
            for item in value
        ]

    return value


def _safe_url_path(url: Optional[str]) -> Optional[str]:
    """Reduces a URL to its path only -- query strings may carry tokens or
    verification codes, so they are dropped entirely."""
    if not url or not isinstance(url, str):
        return url
    return url.split("?", 1)[0].split("#", 1)[0]


def redact_breadcrumb(breadcrumb: dict) -> dict:
    """Scrub SDK-generated HTTP/log breadcrumb metadata before delivery.

    The live E09-04 audit confirmed that backend events include SDK-generated
    HTTP breadcrumbs in addition to the top-level request.  Those breadcrumbs
    must pass through the same URL/header redaction policy so alert emails and
    issue previews cannot bypass the top-level request safeguards.
    """
    redacted = dict(breadcrumb)
    data = redacted.get("data")
    if isinstance(data, dict):
        safe_data = redact_deep(data)
        if isinstance(safe_data, dict) and isinstance(safe_data.get("url"), str):
            safe_data["url"] = _safe_url_path(safe_data["url"])
        redacted["data"] = safe_data
    return redacted


def redact_event(event: dict, hint: dict) -> dict:
    """Sentry before_send hook. Never sent by default, regardless of
    content: full request bodies, Authorization/Cookie headers, query
    strings, exact coordinates, or any key matching the sensitive pattern
    above, anywhere in the event (extra, contexts, request)."""
    # The Python SDK populates ``server_name`` from ``socket.gethostname()``
    # by default.  Container/host identifiers are not needed for grouping or
    # debugging this service, so never send them.
    event.pop("server_name", None)

    # Geography may be attached by an SDK event processor.  Sentry's
    # project-level "Prevent Storing of IP Addresses" setting is the primary
    # protection against server-side IP enrichment; these removals are a
    # defense in depth for geo data already present in the event payload.
    event.pop("geo", None)

    request = event.get("request")
    if isinstance(request, dict):
        if "data" in request:
            del request["data"]
        if "cookies" in request:
            del request["cookies"]
        if "query_string" in request:
            del request["query_string"]
        if "url" in request:
            request["url"] = _safe_url_path(request["url"])
        if "headers" in request:
            request["headers"] = redact_deep(request["headers"])

    if "extra" in event:
        event["extra"] = redact_deep(event["extra"])
    if "contexts" in event:
        event["contexts"] = redact_deep(event["contexts"])
        if isinstance(event["contexts"], dict):
            event["contexts"].pop("geo", None)

    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, list):
        event["breadcrumbs"] = [
            redact_breadcrumb(item) if isinstance(item, dict) else item
            for item in breadcrumbs
        ]

    user = event.get("user")
    if isinstance(user, dict):
        # Only the internal id is ever set (see capture_unexpected_exception
        # below); strip anything else defensively.
        event["user"] = {"id": user["id"]} if user.get("id") else None

    return remove_command_line_arguments(event)


def init_monitoring(settings: Settings) -> None:
    """Must be called during FastAPI startup, before the app begins serving
    requests. A missing DSN, a disabled environment, or an SDK
    initialization failure all resolve to the same safe outcome: the API
    starts normally and capture_unexpected_exception becomes a no-op."""
    global _enabled

    environment = resolve_environment(settings.sentry_environment)
    release = resolve_release(settings.sentry_release)
    enabled = is_monitoring_enabled(
        settings.sentry_dsn, environment, settings.sentry_enabled
    )

    if not enabled:
        _enabled = False
        return

    try:
        sample_rate = trace_sample_rate(environment)
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=environment,
            release=release,
            send_default_pii=False,
            include_local_variables=False,
            traces_sample_rate=sample_rate,
            before_send=redact_event,
            before_send_transaction=before_send_transaction,
            # Disabled: both integrations default to auto-capturing any
            # response with a 5xx status code, which would double-report
            # every event this module already captures explicitly and
            # deliberately from app/main.py's exception handlers (the single
            # chosen capture point, so redaction/tagging is guaranteed to
            # run exactly once).
            integrations=[
                StarletteIntegration(failed_request_status_codes=set()),
                FastApiIntegration(failed_request_status_codes=set()),
            ],
        )
        _enabled = True
    except Exception:  # noqa: BLE001 - initialization must never crash startup
        logger.warning("Sentry initialization failed; continuing without crash reporting.", exc_info=True)
        _enabled = False


def is_monitoring_active() -> bool:
    return _enabled


def capture_unexpected_exception(
    exc: BaseException,
    *,
    request_id: Optional[str] = None,
    route: Optional[str] = None,
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    code: Optional[str] = None,
) -> Optional[str]:
    """The single point unexpected backend exceptions are reported from.
    Safe tags only -- never raw user-provided text or request content."""
    if not _enabled:
        return None
    try:
        with sentry_sdk.new_scope() as scope:
            if request_id:
                scope.set_tag("request_id", request_id)
            if route:
                scope.set_tag("endpoint", route)
            if method:
                scope.set_tag("http_method", method)
            if status_code:
                scope.set_tag("http_status", status_code)
            if code:
                scope.set_tag("error_code", code)
            return sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001 - a reporting failure must never break the API
        logger.warning("Sentry capture_exception call failed; ignoring.", exc_info=True)
        return None


def capture_unexpected_message(message: str, level: str = "warning", **tags: Any) -> Optional[str]:
    if not _enabled:
        return None
    try:
        with sentry_sdk.new_scope() as scope:
            for key, value in tags.items():
                if value is not None:
                    scope.set_tag(key, value)
            return sentry_sdk.capture_message(message, level=level)
    except Exception:  # noqa: BLE001
        logger.warning("Sentry capture_message call failed; ignoring.", exc_info=True)
        return None
