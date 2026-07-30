from __future__ import annotations

from collections.abc import Callable
from json import JSONDecodeError
from typing import Any

import httpx
import pytest
from postgrest import SyncPostgrestClient
from postgrest.base_request_builder import SingleAPIResponse
from postgrest.exceptions import APIError
from pydantic import ValidationError

from app.services.postgrest_mutation_outcomes import execute_postgrest_mutation


PRIVATE_RESPONSE_SENTINEL = "postgrest-private-response-sentinel"


class ControlledSession:
    def __init__(
        self,
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> None:
        self.handler = handler

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any],
        params: Any,
        headers: Any,
    ) -> httpx.Response:
        request = httpx.Request(
            method,
            f"https://postgrest-contract.invalid{path}",
            json=json,
            params=params,
            headers=headers,
        )
        return self.handler(request)


def _rpc_operation(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[[], SingleAPIResponse[Any]]:
    client = SyncPostgrestClient("https://postgrest-contract.invalid")
    client.session.close()
    client.session = ControlledSession(handler)  # type: ignore[assignment]
    return lambda: client.rpc("contract_mutation", {"p_value": "bounded"}).execute()


def _validated_success(response: Any) -> str | None:
    data = response.data
    if (
        isinstance(data, list)
        and len(data) == 1
        and data[0] == {"result": "confirmed"}
    ):
        return "confirmed"
    return None


def _json_response(
    status_code: int,
    payload: Any,
) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(
        status_code,
        json=payload,
        request=request,
    )


def _malformed_json_response(
    status_code: int,
) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(
        status_code,
        content=PRIVATE_RESPONSE_SENTINEL.encode(),
        headers={"content-type": "application/json"},
        request=request,
    )


def test_real_builder_confirms_valid_2xx_response() -> None:
    operation = _rpc_operation(
        _json_response(200, [{"result": "confirmed"}]),
    )

    response = operation()
    assert isinstance(response, SingleAPIResponse)
    assert response.data == [{"result": "confirmed"}]

    result = execute_postgrest_mutation(
        operation,
        validate_response=_validated_success,
    )
    assert result.state == "confirmed_succeeded"
    assert result.response == "confirmed"
    assert result.failure_category is None
    assert result.ambiguity_reason is None


def test_real_builder_2xx_malformed_json_is_ambiguous() -> None:
    operation = _rpc_operation(_malformed_json_response(200))

    response = operation()
    assert isinstance(response, SingleAPIResponse)
    assert response.data == PRIVATE_RESPONSE_SENTINEL

    result = execute_postgrest_mutation(
        operation,
        validate_response=_validated_success,
    )
    assert result.state == "outcome_ambiguous"
    assert result.response is None
    assert result.failure_category is None
    assert result.ambiguity_reason == "response_processing_failure"


def test_real_builder_2xx_validation_failure_is_ambiguous() -> None:
    operation = _rpc_operation(
        _json_response(
            200,
            {
                "code": "XX000",
                "message": PRIVATE_RESPONSE_SENTINEL,
                "details": PRIVATE_RESPONSE_SENTINEL,
                "hint": PRIVATE_RESPONSE_SENTINEL,
            },
        )
    )

    with pytest.raises(APIError) as exc_info:
        operation()
    assert isinstance(exc_info.value.__cause__, ValidationError)
    assert exc_info.value.__context__ is exc_info.value.__cause__

    result = execute_postgrest_mutation(
        operation,
        validate_response=_validated_success,
    )
    assert result.state == "outcome_ambiguous"
    assert result.failure_category is None
    assert result.ambiguity_reason == "response_processing_failure"


@pytest.mark.parametrize(
    ("code", "expected_category"),
    [
        ("08006", "service_unavailable"),
        ("PGRST202", "invalid_state"),
        ("XX000", "internal_error"),
    ],
)
def test_real_builder_structured_non_2xx_confirms_rollback(
    code: str,
    expected_category: str,
) -> None:
    operation = _rpc_operation(
        _json_response(
            500,
            {
                "code": code,
                "message": PRIVATE_RESPONSE_SENTINEL,
                "details": PRIVATE_RESPONSE_SENTINEL,
                "hint": PRIVATE_RESPONSE_SENTINEL,
            },
        )
    )

    with pytest.raises(APIError) as exc_info:
        operation()
    assert exc_info.value.code == code
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None

    result = execute_postgrest_mutation(
        operation,
        validate_response=_validated_success,
    )
    assert result.state == "confirmed_failed"
    assert result.failure_category == expected_category
    assert result.ambiguity_reason is None


def test_real_builder_non_2xx_malformed_json_is_ambiguous() -> None:
    operation = _rpc_operation(_malformed_json_response(500))

    with pytest.raises(APIError) as exc_info:
        operation()
    assert exc_info.value.__cause__ is None
    assert isinstance(exc_info.value.__context__, JSONDecodeError)

    result = execute_postgrest_mutation(
        operation,
        validate_response=_validated_success,
    )
    assert result.state == "outcome_ambiguous"
    assert result.failure_category is None
    assert result.ambiguity_reason == "response_processing_failure"


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_real_builder_transport_failure_is_ambiguous(
    error_type: type[httpx.RequestError],
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise error_type(PRIVATE_RESPONSE_SENTINEL, request=request)

    operation = _rpc_operation(fail)
    with pytest.raises(error_type) as exc_info:
        operation()
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None

    result = execute_postgrest_mutation(
        operation,
        validate_response=_validated_success,
    )
    assert result.state == "outcome_ambiguous"
    assert result.failure_category is None
    assert result.ambiguity_reason == "transport_failure"


def test_real_builder_does_not_classify_from_exception_message_text() -> None:
    operation = _rpc_operation(
        _json_response(
            500,
            {
                "code": "not-structured",
                "message": "XX000 PGRST202 08006",
                "details": PRIVATE_RESPONSE_SENTINEL,
                "hint": PRIVATE_RESPONSE_SENTINEL,
            },
        )
    )

    result = execute_postgrest_mutation(
        operation,
        validate_response=_validated_success,
    )
    assert result.state == "outcome_ambiguous"
    assert result.failure_category is None
    assert result.ambiguity_reason == "response_processing_failure"
