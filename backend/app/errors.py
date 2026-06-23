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
