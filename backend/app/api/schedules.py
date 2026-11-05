"""Admin-only schedule configuration; REST endpoints NEVER enqueue a job."""
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.models import AuditLog, OnionSource, SourceSchedule, ScheduleDecision
from app.schemas.schedule import ScheduleConfigure, ScheduleOut, SchedulePause, ScheduleDecisionOut
from app.security.api_key import require_api_key, require_role

router = APIRouter(prefix="/api/v1/schedules", tags=["schedules"],
                   dependencies=[Depends(require_api_key), Depends(require_role("ADMIN"))])


def _audit(db: Session, source_id: uuid.UUID, action: str, *, reason: str, enabled: bool) -> None:
    db.add(AuditLog(actor=db.info.get("actor", "api_key_operator"), action=action,
                    entity_type="onion_source", entity_id=source_id,
                    details=json.dumps({"reason": reason, "enabled": enabled})))


@router.get("/{source_id}", response_model=ScheduleOut)
def get_schedule(source_id: uuid.UUID, db: Session = Depends(get_session)) -> SourceSchedule:
    schedule = db.get(SourceSchedule, source_id)
    if schedule is None:
        raise HTTPException(404, "Aucune planification pour cette source")
    return schedule


@router.put("/{source_id}", response_model=ScheduleOut)
def configure_schedule(source_id: uuid.UUID, data: ScheduleConfigure,
                       db: Session = Depends(get_session)) -> SourceSchedule:
    # Same row lock order as dispatch: source then schedule.
    source = db.scalar(select(OnionSource).where(OnionSource.id == source_id).with_for_update())
    if source is None or source.deleted_at is not None:
        raise HTTPException(404, "Source introuvable")
    if data.enabled and not (source.is_active and source.approved_for_collection and source.collection_enabled):
        raise HTTPException(409, "La source ne permet pas une planification active")
    schedule = db.scalar(select(SourceSchedule).where(SourceSchedule.source_id == source_id).with_for_update())
    now = datetime.now(timezone.utc)
    if schedule is None:
        schedule = SourceSchedule(source_id=source_id, next_run_at=now)
        db.add(schedule)
    elif not schedule.enabled or not data.enabled:
        schedule.next_run_at = now
    # Updating an enabled schedule never moves its next run earlier.
    for field in ("enabled", "interval_minutes", "daily_budget", "window_start_hour", "window_end_hour",
                  "expires_at", "approval_reference"):
        setattr(schedule, field, getattr(data, field))
    _audit(db, source_id, "schedule.configure", reason=data.reason, enabled=data.enabled)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.post("/{source_id}/pause", response_model=ScheduleOut)
def pause_schedule(source_id: uuid.UUID, data: SchedulePause,
                   db: Session = Depends(get_session)) -> SourceSchedule:
    source = db.scalar(select(OnionSource).where(OnionSource.id == source_id).with_for_update())
    if source is None or source.deleted_at is not None:
        raise HTTPException(404, "Source introuvable")
    schedule = db.scalar(select(SourceSchedule).where(SourceSchedule.source_id == source_id).with_for_update())
    if schedule is None:
        raise HTTPException(404, "Aucune planification pour cette source")
    if schedule.enabled:
        schedule.enabled = False
        _audit(db, source_id, "schedule.pause", reason=data.reason, enabled=False)
        db.commit()
        db.refresh(schedule)
    return schedule


@router.get("/{source_id}/decisions", response_model=list[ScheduleDecisionOut])
def schedule_decisions(source_id: uuid.UUID, limit: int = Query(50, ge=1, le=100),
                       db: Session = Depends(get_session)) -> list[ScheduleDecision]:
    return list(db.scalars(select(ScheduleDecision).where(ScheduleDecision.source_id == source_id)
                           .order_by(ScheduleDecision.created_at.desc(), ScheduleDecision.id.desc())
                           .limit(limit)).all())
