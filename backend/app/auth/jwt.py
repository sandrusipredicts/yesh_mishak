from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status

from app.core.config import get_settings


def create_access_token(subject: str, email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": subject,
        "email": email,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()

    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc
