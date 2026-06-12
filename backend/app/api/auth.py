from fastapi import APIRouter, HTTPException, status

from app.auth.google import find_or_create_google_user, verify_google_token
from app.auth.jwt import create_access_token
from app.schemas.auth import GoogleAuthRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=TokenResponse)
def google_login(payload: GoogleAuthRequest) -> TokenResponse:
    google_user = verify_google_token(payload.token)
    user = find_or_create_google_user(google_user)

    user_id = user.get("id")
    email = user.get("email")
    name = user.get("name")

    if not user_id or not email or not name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User record is missing required fields",
        )

    access_token = create_access_token(subject=str(user_id), email=email)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(id=str(user_id), email=email, name=name),
    )
