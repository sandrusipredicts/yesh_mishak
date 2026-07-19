from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi import UploadFile, status

from app.errors import raise_api_error

FIELD_PHOTO_BUCKET = "field-photos"
FIELD_PHOTO_MAX_BYTES = 5 * 1024 * 1024
FIELD_PHOTO_ALLOWED_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
FIELD_PHOTO_READ_LIMIT = FIELD_PHOTO_MAX_BYTES + 1


@dataclass(frozen=True)
class ValidatedFieldPhoto:
    content: bytes
    mime_type: str
    extension: str


def detect_image_mime(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


async def validate_field_photo_upload(upload: UploadFile) -> ValidatedFieldPhoto:
    content = await upload.read(FIELD_PHOTO_READ_LIMIT)
    if not content:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="FIELD_PHOTO_EMPTY",
            message="Field photo is empty",
        )
    if len(content) > FIELD_PHOTO_MAX_BYTES:
        raise_api_error(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="FIELD_PHOTO_TOO_LARGE",
            message="Field photo is too large",
            details={"max_bytes": FIELD_PHOTO_MAX_BYTES},
        )

    detected_mime = detect_image_mime(content)
    if detected_mime not in FIELD_PHOTO_ALLOWED_MIME_TYPES:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="FIELD_PHOTO_UNSUPPORTED_TYPE",
            message="Unsupported field photo type",
            details={"allowed_types": sorted(FIELD_PHOTO_ALLOWED_MIME_TYPES)},
        )

    return ValidatedFieldPhoto(
        content=content,
        mime_type=detected_mime,
        extension=FIELD_PHOTO_ALLOWED_MIME_TYPES[detected_mime],
    )


def build_field_photo_path(field_id: str, extension: str) -> str:
    safe_extension = extension.lower().lstrip(".")
    if safe_extension not in set(FIELD_PHOTO_ALLOWED_MIME_TYPES.values()):
        raise ValueError("unsupported field photo extension")
    return f"fields/{field_id}/{uuid4().hex}.{safe_extension}"


def upload_field_photo(storage_client, photo: ValidatedFieldPhoto, *, field_id: str) -> str:
    path = build_field_photo_path(field_id, photo.extension)
    storage_client.storage.from_(FIELD_PHOTO_BUCKET).upload(
        path,
        photo.content,
        {
            "content-type": photo.mime_type,
            "x-upsert": "false",
        },
    )
    return path


def remove_field_photo(storage_client, path: str | None) -> None:
    if not path:
        return
    storage_client.storage.from_(FIELD_PHOTO_BUCKET).remove([path])


def create_field_photo_signed_url(storage_client, path: str, expires_in: int = 3600) -> str | None:
    response = storage_client.storage.from_(FIELD_PHOTO_BUCKET).create_signed_url(path, expires_in)
    if isinstance(response, dict):
        return response.get("signedURL") or response.get("signedUrl") or response.get("signed_url")
    if isinstance(response, str):
        return response
    return None
