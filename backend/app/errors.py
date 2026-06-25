from fastapi import HTTPException
from typing import Any, Dict, Optional

def error_response(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Returns the unified error response shape.
    """
    response = {
        "error": True,
        "code": code,
        "message": message
    }
    if details is not None:
        response["details"] = details
    return response

def raise_api_error(status_code: int, code: str, message: str, details: Optional[Dict[str, Any]] = None):
    """
    Raises a FastAPI HTTPException with a standardized payload.
    """
    raise HTTPException(
        status_code=status_code,
        detail=error_response(code, message, details)
    )


import re
from fastapi import status

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)

import os

def validate_uuid_id(value: str | None, name: str = "id") -> str:
    if not value or not isinstance(value, str):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_ID",
            message=f"Invalid {name} format. Must be a valid UUID.",
        )

    is_valid_uuid = bool(UUID_PATTERN.match(value))

    # Allow common mock IDs (e.g. 'game-1', 'creator-1') only during tests
    # when ALLOW_TEST_MOCK_IDS=true is explicitly set in environment configuration.
    allow_mock = os.environ.get("ALLOW_TEST_MOCK_IDS") == "true"
    is_allowed_mock = False
    if allow_mock:
        allowed_prefixes = (
            "game-", "field-", "user-", "report-", "notification-", "notifications-",
            "admin-", "creator-", "other-", "member-", "player-",
            "test-", "mock-", "tok-", "token-", "candidate-", "reporter-",
            "closed-", "renovation-", "missing-", "notif-", "reno-"
        )
        if value.startswith(allowed_prefixes):
            is_allowed_mock = True

    if not is_valid_uuid and not is_allowed_mock:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_ID",
            message=f"Invalid {name} format. Must be a valid UUID.",
        )
    return value
