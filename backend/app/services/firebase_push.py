from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import google.auth
import requests
from google.auth.transport.requests import Request
from google.auth.credentials import Credentials
from google.auth.exceptions import DefaultCredentialsError
from google.oauth2 import service_account

from app.core.config import get_settings

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
INVALID_TOKEN_ERROR_CODES = {
    "INVALID_ARGUMENT",
    "NOT_FOUND",
    "UNREGISTERED",
    "SENDER_ID_MISMATCH",
}


class FirebaseConfigError(RuntimeError):
    pass


def _load_service_account_info() -> dict[str, Any]:
    settings = get_settings()

    if settings.firebase_service_account_json:
        try:
            return json.loads(settings.firebase_service_account_json)
        except json.JSONDecodeError as exc:
            raise FirebaseConfigError("FIREBASE_SERVICE_ACCOUNT_JSON is invalid JSON") from exc

    if settings.firebase_service_account_file:
        try:
            with open(settings.firebase_service_account_file, encoding="utf-8") as credentials_file:
                return json.load(credentials_file)
        except OSError as exc:
            raise FirebaseConfigError("FIREBASE_SERVICE_ACCOUNT_FILE could not be read") from exc
        except json.JSONDecodeError as exc:
            raise FirebaseConfigError("FIREBASE_SERVICE_ACCOUNT_FILE is invalid JSON") from exc

    raise FirebaseConfigError("Firebase service account credentials are not configured")


@lru_cache
def _get_credentials() -> Credentials:
    settings = get_settings()

    if settings.firebase_service_account_json or settings.firebase_service_account_file:
        return service_account.Credentials.from_service_account_info(
            _load_service_account_info(),
            scopes=[FCM_SCOPE],
        )

    try:
        credentials, _ = google.auth.default(scopes=[FCM_SCOPE])
    except DefaultCredentialsError as exc:
        raise FirebaseConfigError(
            "Firebase ADC credentials are not available. Run "
            "'gcloud auth application-default login' or configure a backend "
            "service account credential source."
        ) from exc

    return credentials


def _get_access_token() -> str:
    credentials = _get_credentials()

    if not credentials.valid:
        credentials.refresh(Request())

    return credentials.token


def _get_project_id() -> str:
    settings = get_settings()

    if settings.firebase_project_id:
        return settings.firebase_project_id

    if settings.firebase_service_account_json or settings.firebase_service_account_file:
        project_id = _load_service_account_info().get("project_id")
        if project_id:
            return str(project_id)

    try:
        _, project_id = google.auth.default(scopes=[FCM_SCOPE])
    except DefaultCredentialsError:
        project_id = None

    if project_id:
        return project_id

    raise FirebaseConfigError("FIREBASE_PROJECT_ID is not configured")


def _is_invalid_token_response(response: requests.Response) -> bool:
    if response.status_code in (400, 404):
        try:
            payload = response.json()
        except ValueError:
            return False

        error = payload.get("error") or {}
        if str(error.get("status") or "") in INVALID_TOKEN_ERROR_CODES:
            return True

        for detail in error.get("details") or []:
            error_code = str(detail.get("errorCode") or "")
            if error_code in INVALID_TOKEN_ERROR_CODES:
                return True

    return False


def send_fcm_notification(
    token: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_id = _get_project_id()
    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    message_data = {
        key: str(value)
        for key, value in (data or {}).items()
        if value is not None
    }
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {_get_access_token()}",
            "Content-Type": "application/json",
        },
        json={
            "message": {
                "token": token,
                "notification": {
                    "title": title,
                    "body": body,
                },
                "data": message_data,
            }
        },
        timeout=10,
    )

    if _is_invalid_token_response(response):
        return {"ok": False, "invalid_token": True, "status_code": response.status_code}

    response.raise_for_status()
    return {"ok": True, "response": response.json()}
