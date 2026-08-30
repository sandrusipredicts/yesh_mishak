from fastapi import APIRouter

from app.services.business_branding import get_business_branding

router = APIRouter(prefix="/branding", tags=["branding"])


@router.get("")
def get_public_branding():
    return get_business_branding()
