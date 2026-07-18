"""Small, self-contained request-correlation-id middleware (E09-01).

Deliberately minimal: accepts a client-supplied X-Request-Id (bounded
length, no broad middleware/API redesign), or generates one, stores it on
request.state, and echoes it back in the response header. Exception
handlers in app/main.py read request.state.request_id to tag the matching
Sentry event, so a frontend-reported error and its backend counterpart can
be cross-referenced by this id. Never derived from a user/session token.
"""
import re
import uuid
from typing import Awaitable, Callable

from fastapi import Request, Response

REQUEST_ID_HEADER = "X-Request-Id"
_SAFE_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _resolve_request_id(request: Request) -> str:
    incoming = request.headers.get(REQUEST_ID_HEADER)
    if incoming and _SAFE_REQUEST_ID_PATTERN.match(incoming):
        return incoming
    return str(uuid.uuid4())


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = _resolve_request_id(request)
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
