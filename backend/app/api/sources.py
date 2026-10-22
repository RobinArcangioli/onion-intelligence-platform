from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import AuditLog, OnionSource
from app.schemas.source import SourceCreate, SourceList, SourceOut
from app.security.api_key import require_api_key

router = APIRouter(prefix="/api/v1/sources", tags=["sources"],
                   dependencies=[Depends(require_api_key)])


@router.get("", response_model=SourceList)
def list_sources(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_session),
) -> SourceList:
    total = db.scalar(select(func.count()).select_from(OnionSource)) or 0
    sources = db.scalars(select(OnionSource).order_by(OnionSource.created_at, OnionSource.id)
                         .offset(offset).limit(limit)).all()
    return SourceList(total=total, items=[SourceOut.model_validate(x) for x in sources])


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreate, db: Session = Depends(get_session)) -> OnionSource:
    source = OnionSource(
        canonical_url=payload.url, name=payload.name,
        description=payload.description,
        authorization_note=payload.authorization_note,
        approved_for_collection=True,
        collection_enabled=False,  # aucun moteur de collecte en phase 1
    )
    try:
        db.add(source)
        db.flush()
        db.add(AuditLog(actor="api_key_operator", action="source.create",
                        entity_type="onion_source", entity_id=source.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Source déjà enregistrée") from exc
    db.refresh(source)
    return source
