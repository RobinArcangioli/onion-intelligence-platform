"""Metadata search and comparisons. No HTML, body text or network access."""
from datetime import datetime, timezone
import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import CrawlJob, OnionSource, SourceObservation
from app.schemas.collection import ObservationOut

# Deliberate search scope: bounded title/description ONLY. The transient
# extracted page text is never persisted and cannot be searched retrospectively.
COMPARABLE = ("title", "description", "http_status", "content_type", "response_bytes",
              "text_length", "text_sha256", "relevance_score", "keyword_hits", "discovered_links")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _time(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def search(db: Session, *, source_id: uuid.UUID | None, category: str | None,
           status: str | None, since: datetime | None, until: datetime | None,
           q: str | None, sha256: str | None, limit: int, offset: int) -> dict:
    filters = []
    if source_id is not None:
        filters.append(SourceObservation.source_id == source_id)
    if category:
        filters.append(OnionSource.category == category)
    if status:
        filters.append(SourceObservation.change_status == status)
    if since:
        filters.append(SourceObservation.created_at >= since)
    if until:
        filters.append(SourceObservation.created_at < until)
    if sha256:
        filters.append(SourceObservation.text_sha256 == sha256)
    if q:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            # All input values are bound parameters; fixed English-independent
            # lexemes, same indexed expression as migration 0011.
            document = func.to_tsvector('simple', func.coalesce(SourceObservation.title, '') +
                                        ' ' + func.coalesce(SourceObservation.description, ''))
            filters.append(document.op('@@')(func.plainto_tsquery('simple', q)))
        else:
            pattern = f"%{_escape_like(q.lower())}%"
            filters.append(or_(func.lower(SourceObservation.title).like(pattern, escape='\\'),
                               func.lower(SourceObservation.description).like(pattern, escape='\\')))
    # Avoid a join while counting unless the source category is filtered.
    # The paginated result still joins once to return source display names.
    count_stmt = select(func.count(SourceObservation.id))
    if category:
        count_stmt = count_stmt.join(OnionSource, OnionSource.id == SourceObservation.source_id)
    total = db.scalar(count_stmt.where(*filters)) or 0
    rows = db.execute(select(SourceObservation, OnionSource.name, OnionSource.category)
                      .join(OnionSource, OnionSource.id == SourceObservation.source_id)
                      .where(*filters)
                      .order_by(SourceObservation.created_at.desc(), SourceObservation.id.desc())
                      .offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "search_scope": "title_and_description_only",
            "items": [{**ObservationOut.model_validate(row).model_dump(mode='json'),
                       "source_name": name, "source_category": cat}
                      for row, name, cat in rows]}


def provenance(db: Session, observation: SourceObservation) -> dict:
    # The ordering is stable even when several records share a timestamp.
    prev = db.scalar(select(SourceObservation).where(
        SourceObservation.source_id == observation.source_id,
        or_(SourceObservation.created_at < observation.created_at,
            and_(SourceObservation.created_at == observation.created_at,
                 SourceObservation.id < observation.id)))
        .order_by(SourceObservation.created_at.desc(), SourceObservation.id.desc()).limit(1))
    job = db.get(CrawlJob, observation.job_id)
    source = db.get(OnionSource, observation.source_id)
    # The source and job FKs should exist. Do not leak a broken data join as 500.
    changes = ({key: {"before": getattr(prev, key), "after": getattr(observation, key)}
                for key in COMPARABLE if getattr(prev, key) != getattr(observation, key)} if prev else {})
    return {
        "observation": ObservationOut.model_validate(observation).model_dump(mode='json'),
        "source": {"id": str(observation.source_id), "name": source.name if source else None,
                   "category": source.category if source else None},
        "job": {"id": str(observation.job_id), "status": job.status if job else None,
                "started_at": _time(job.started_at).isoformat() if job and job.started_at else None,
                "finished_at": _time(job.finished_at).isoformat() if job and job.finished_at else None},
        "previous_observation_id": str(prev.id) if prev else None,
        "hash_changed": prev.text_sha256 != observation.text_sha256 if prev else None,
        "metadata_changes": changes,
        "comparison_scope": "hash_and_retained_metadata_only",
        "limitations": "Changes in page text are detected by SHA-256, not a semantic text diff. "
                       "No raw page text is retained; a hash change is not evidence of malicious activity.",
    }
