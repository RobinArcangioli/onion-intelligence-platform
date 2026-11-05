"""Read-only investigation endpoints over deliberately minimal metadata."""
from datetime import datetime, timedelta, timezone
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import SourceObservation
from app.observation_history.service import provenance, search
from app.observation_history.retention import impact_preview
from app.security.api_key import require_api_key, require_role

router = APIRouter(prefix="/api/v1/observations", tags=["observations"],
                   dependencies=[Depends(require_api_key)])


@router.get("/search")
def search_observations(
    source_id: uuid.UUID | None = None,
    category: str | None = Query(None, min_length=1, max_length=60),
    change_status: str | None = Query(None, pattern="^(FIRST_SEEN|UNCHANGED|MODIFIED|UNKNOWN)$"),
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = Query(None, min_length=2, max_length=120),
    sha256: str | None = Query(None, pattern=r"^[0-9a-f]{64}$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_session),
) -> dict:
    if (since is not None and since.tzinfo is None) or (until is not None and until.tzinfo is None):
        raise HTTPException(422, "Dates must include a timezone")
    if since and until and since >= until:
        raise HTTPException(422, "since must be before until")
    if q is not None:
        q = " ".join(q.split())
        if len(q) < 2 or not re.search(r"\w", q, re.UNICODE):
            raise HTTPException(422, "Search must contain meaningful characters")
    return search(db, source_id=source_id, category=category, status=change_status,
                  since=since, until=until, q=q, sha256=sha256, limit=limit, offset=offset)


@router.get("/retention/preview", dependencies=[Depends(require_role("ADMIN"))])
def preview_retention(older_than_days: int = Query(90, ge=30, le=3650),
                      source_id: uuid.UUID | None = None,
                      db: Session = Depends(get_session)) -> dict:
    """Read-only impact counts; never executes a purge or cascades to audit."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    return impact_preview(db, cutoff=cutoff, older_than_days=older_than_days,
                          source_id=source_id)


@router.get("/{observation_id}/provenance")
def observation_provenance(observation_id: uuid.UUID, db: Session = Depends(get_session)) -> dict:
    observation = db.get(SourceObservation, observation_id)
    if observation is None:
        raise HTTPException(404, "Observation not found")
    return provenance(db, observation)
