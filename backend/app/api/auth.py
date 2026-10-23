"""Non-secret identity information for the active credential."""
from fastapi import APIRouter, Depends
from app.security.api_key import Principal, require_api_key

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me")
def me(principal: Principal = Depends(require_api_key)) -> dict[str, str | bool]:
    return {"username": principal.username, "role": principal.role, "legacy": principal.legacy}
