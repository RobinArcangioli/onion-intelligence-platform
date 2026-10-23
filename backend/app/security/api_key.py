"""Named, revocable API keys with RBAC. No browser cookies or persistent sessions."""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.identity import Operator, OperatorToken

ROLE_LEVEL = {"VIEWER": 1, "ANALYST": 2, "ADMIN": 3}


@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    legacy: bool = False


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return "oip_" + secrets.token_urlsafe(32)


def require_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_session),
) -> Principal:
    if not x_api_key or len(x_api_key) > 256:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    expected = settings.api_key.get_secret_value()
    if settings.legacy_api_key_enabled and secrets.compare_digest(x_api_key, expected):
        db.info["actor"] = "legacy_operator"
        return Principal(username="legacy_operator", role="ADMIN", legacy=True)
    if not x_api_key.startswith("oip_") or len(x_api_key) < 36:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    token = db.scalar(select(OperatorToken).where(OperatorToken.token_hash == fingerprint(x_api_key)))
    if token is None or token.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    expiry = token.expires_at
    if expiry.tzinfo is None:  # SQLite stores naive timestamps; PostgreSQL is aware.
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Expired API key")
    user = db.get(Operator, token.operator_id)
    if user is None or not user.active or user.role not in ROLE_LEVEL:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive operator")
    db.info["actor"] = user.username
    return Principal(username=user.username, role=user.role)


def require_role(minimum: str) -> Callable:
    if minimum not in ROLE_LEVEL:
        raise ValueError("Unknown role")

    def check(principal: Principal = Depends(require_api_key)) -> Principal:
        if ROLE_LEVEL[principal.role] < ROLE_LEVEL[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return principal

    return check
