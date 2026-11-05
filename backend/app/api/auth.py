"""Non-secret identity and personal credential inventory for the active user.

No API route issues a plaintext credential: issuance and rotation require the
local administrative CLI. The legacy shared key cannot list operator tokens.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.identity import Operator, OperatorToken
from app.security.api_key import Principal, fingerprint, require_api_key

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me")
def me(principal: Principal = Depends(require_api_key)) -> dict[str, str | bool]:
    return {"username": principal.username, "role": principal.role, "legacy": principal.legacy}


@router.get("/tokens")
def my_tokens(
    principal: Principal = Depends(require_api_key),
    db: Session = Depends(get_session),
    x_api_key: str = Header(),
    limit: int = Query(25, ge=1, le=50),
    offset: int = Query(0, ge=0),
) -> dict:
    """Paginated inventory of ONLY the authenticated operator's token metadata."""
    if principal.legacy:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Named operator required")
    operator = db.scalar(select(Operator).where(Operator.username == principal.username))
    if operator is None or not operator.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive operator")
    query = select(OperatorToken).where(OperatorToken.operator_id == operator.id)
    total = db.scalar(select(func.count()).select_from(OperatorToken).where(
        OperatorToken.operator_id == operator.id,
    )) or 0
    tokens = db.scalars(query.order_by(OperatorToken.created_at.desc(), OperatorToken.id.desc())
                        .limit(limit).offset(offset)).all()
    now = datetime.now(timezone.utc)
    current_fingerprint = fingerprint(x_api_key)
    items = []
    for token in tokens:
        expiry = token.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        state = "REVOKED" if token.revoked_at is not None else (
            "EXPIRED" if expiry <= now else "ACTIVE"
        )
        items.append({
            "id": str(token.id),
            "label": token.label,
            "created_at": token.created_at.isoformat() if token.created_at else None,
            "expires_at": expiry.isoformat(),
            "status": state,
            "current": token.token_hash == current_fingerprint,
        })
    return {"items": items, "total": total, "limit": limit, "offset": offset}
