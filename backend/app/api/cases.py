"""Human-led alert cases; safe, version-checked commands and metadata-only audit."""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import Alert, AnalystCase, AnalystCaseEvent, AnalystCaseNote, AuditLog, Operator
from app.schemas.case import CaseCommand, CaseCreate, CaseEventOut, CaseOut, CaseNoteCreate, CaseNoteOut
from app.security.api_key import Principal, require_role

router = APIRouter(prefix="/api/v1/cases", tags=["analyst-cases"],
                   dependencies=[Depends(require_role("ANALYST"))])

TRANSITIONS = {
    "START_REVIEW": ("OPEN", "IN_REVIEW"),
    "ESCALATE": ("IN_REVIEW", "ESCALATED"),
    "RETURN_REVIEW": ("ESCALATED", "IN_REVIEW"),
}


def _may_write_case(db: Session, row: AnalystCase, actor: Principal, action: str, assignee: str | None = None) -> None:
    """Assigned cases are single-writer for analysts; administrators can reassign.

    Unassigned cases can be triaged by any analyst, but analyst assignment is
    exclusively self-claim. The compare-and-swap version blocks stale writers.
    """
    if actor.role == "ADMIN":
        return
    if row.assignee_id is not None:
        owner = db.get(Operator, row.assignee_id)
        if owner is None or owner.username != actor.username:
            raise HTTPException(403, "Case is assigned to another operator")
    if action == "ASSIGN" and (row.assignee_id is not None or assignee != actor.username):
        raise HTTPException(403, "Analysts may only claim unassigned cases for themselves")


def _case(db: Session, case_id: uuid.UUID) -> AnalystCase:
    row = db.get(AnalystCase, case_id)
    if row is None:
        raise HTTPException(404, "Case not found")
    return row


def _render(db: Session, row: AnalystCase) -> CaseOut:
    data = CaseOut.model_validate(row)
    if row.assignee_id is not None:
        user = db.get(Operator, row.assignee_id)
        data.assignee_username = user.username if user else None
    return data


def _event(db: Session, row: AnalystCase, actor: str, action: str,
           from_status: str | None, assignee: str | None = None,
           code: str | None = None):
    db.add(AnalystCaseEvent(case_id=row.id, version=row.version, actor=actor,
                            action=action, from_status=from_status, to_status=row.status,
                            assignee_username=assignee, reason_code=code))
    db.add(AuditLog(actor=actor, action=f"case.{action.lower()}", entity_type="analyst_case",
                    entity_id=row.id,
                    details=json.dumps({"case_version": row.version, "action": action,
                                        "from_status": from_status, "to_status": row.status,
                                        "closure_code": code if action == "CLOSE" else None,
                                        "reason_code": code if action != "CLOSE" else None})))


@router.post("", response_model=CaseOut, status_code=201)
def create_case(payload: CaseCreate, db: Session = Depends(get_session),
                actor: Principal = Depends(require_role("ANALYST"))):
    if db.get(Alert, payload.alert_id) is None:
        raise HTTPException(404, "Alert not found")
    row = AnalystCase(alert_id=payload.alert_id, created_by=actor.username)
    try:
        db.add(row)
        db.flush()
        _event(db, row, actor.username, "CREATE", None)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "A case already exists for this alert") from exc
    db.refresh(row)
    return _render(db, row)


@router.get("", response_model=dict)
def list_cases(status: str | None = Query(None, pattern="^(OPEN|IN_REVIEW|ESCALATED|CLOSED)$"),
               assignee_username: str | None = Query(None, min_length=1, max_length=64),
               alert_id: uuid.UUID | None = None,
               limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
               db: Session = Depends(get_session)):
    criteria = []
    if status is not None:
        criteria.append(AnalystCase.status == status)
    if alert_id is not None:
        criteria.append(AnalystCase.alert_id == alert_id)
    if assignee_username is not None:
        user = db.scalar(select(Operator).where(Operator.username == assignee_username))
        if user is None:
            return {"total": 0, "limit": limit, "offset": offset, "items": []}
        criteria.append(AnalystCase.assignee_id == user.id)
    total = db.scalar(select(func.count()).select_from(AnalystCase).where(*criteria)) or 0
    rows = db.scalars(select(AnalystCase).where(*criteria)
                      .order_by(AnalystCase.updated_at.desc(), AnalystCase.id.desc())
                      .offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [_render(db, row) for row in rows]}


@router.get("/assignees", response_model=list[dict])
def assignees(db: Session = Depends(get_session)):
    rows = db.scalars(select(Operator).where(Operator.active.is_(True),
                                            Operator.role.in_(("ANALYST", "ADMIN")))
                      .order_by(Operator.username).limit(100)).all()
    return [{"username": row.username, "role": row.role} for row in rows]


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: uuid.UUID, db: Session = Depends(get_session)):
    return _render(db, _case(db, case_id))


@router.get("/{case_id}/events", response_model=dict)
def events(case_id: uuid.UUID, limit: int = Query(50, ge=1, le=100),
           offset: int = Query(0, ge=0, le=10000), db: Session = Depends(get_session)):
    _case(db, case_id)
    criteria = AnalystCaseEvent.case_id == case_id
    total = db.scalar(select(func.count()).select_from(AnalystCaseEvent).where(criteria)) or 0
    rows = db.scalars(select(AnalystCaseEvent).where(criteria)
                      .order_by(AnalystCaseEvent.version.desc()).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [CaseEventOut.model_validate(row) for row in rows]}


@router.patch("/{case_id}", response_model=CaseOut)
def change_case(case_id: uuid.UUID, payload: CaseCommand,
                db: Session = Depends(get_session),
                actor: Principal = Depends(require_role("ANALYST"))):
    row = _case(db, case_id)
    if row.version != payload.expected_version:
        raise HTTPException(409, "Stale case version; refresh before updating")
    if row.status == "CLOSED":
        raise HTTPException(409, "Closed cases cannot be changed")
    _may_write_case(db, row, actor, payload.action, payload.assignee_username)

    next_status = row.status
    assigned = None
    updates = {}
    if payload.action == "ASSIGN":
        user = db.scalar(select(Operator).where(Operator.username == payload.assignee_username,
                                                Operator.active.is_(True),
                                                Operator.role.in_(("ANALYST", "ADMIN"))))
        if user is None:
            raise HTTPException(422, "Assignee must be an active analyst or administrator")
        if row.assignee_id == user.id:
            raise HTTPException(409, "Case is already assigned to this operator")
        updates["assignee_id"] = user.id
        assigned = user.username
    elif payload.action == "UNASSIGN":
        if row.assignee_id is None:
            raise HTTPException(409, "Case is not assigned")
        updates["assignee_id"] = None
    elif payload.action == "SET_PRIORITY":
        if row.priority == payload.priority:
            raise HTTPException(409, "Priority is unchanged")
        updates["priority"] = payload.priority
    elif payload.action == "CLOSE":
        if row.status not in ("IN_REVIEW", "ESCALATED"):
            raise HTTPException(409, "Case must be reviewed before closure")
        next_status = "CLOSED"
        updates["closure_code"] = payload.closure_code
        updates["closed_at"] = datetime.now(timezone.utc)
    else:
        expected, next_status = TRANSITIONS[payload.action]
        if row.status != expected:
            raise HTTPException(409, "Invalid case transition")
    if not updates and next_status == row.status:
        raise HTTPException(409, "No changes")
    updates["status"] = next_status
    updates["updated_at"] = datetime.now(timezone.utc)
    updates["version"] = row.version + 1
    # Atomic compare-and-swap even across several API replicas: no lost updates.
    changed = db.execute(update(AnalystCase)
                         .where(AnalystCase.id == row.id, AnalystCase.version == payload.expected_version)
                         .values(**updates).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Stale case version; refresh before updating")
    from_status = row.status
    db.expire(row)
    db.refresh(row)
    _event(db, row, actor.username, payload.action, from_status, assigned,
           payload.closure_code if payload.action == "CLOSE" else
           payload.escalation_reason if payload.action == "ESCALATE" else
           payload.priority if payload.action == "SET_PRIORITY" else None)
    db.commit()
    db.refresh(row)
    return _render(db, row)


@router.post("/{case_id}/notes", response_model=CaseNoteOut, status_code=201)
def add_note(case_id: uuid.UUID, payload: CaseNoteCreate, db: Session = Depends(get_session),
             actor: Principal = Depends(require_role("ANALYST"))):
    row = _case(db, case_id)
    if row.version != payload.expected_version:
        raise HTTPException(409, "Stale case version; refresh before updating")
    if row.status == "CLOSED":
        raise HTTPException(409, "Closed cases cannot be annotated")
    _may_write_case(db, row, actor, "NOTE")
    now = datetime.now(timezone.utc)
    result = db.execute(update(AnalystCase)
                        .where(AnalystCase.id == case_id, AnalystCase.version == payload.expected_version,
                               AnalystCase.status != "CLOSED")
                        .values(version=payload.expected_version + 1, updated_at=now)
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Stale case version; refresh before updating")
    old_status = row.status
    db.expire(row)
    db.refresh(row)
    note = AnalystCaseNote(case_id=case_id, case_version=row.version, actor=actor.username,
                           note_code=payload.note_code, body=payload.body)
    db.add(note)
    _event(db, row, actor.username, "NOTE", old_status, code=payload.note_code)
    db.commit()
    db.refresh(note)
    return CaseNoteOut.model_validate(note)


@router.get("/{case_id}/notes", response_model=dict)
def list_notes(case_id: uuid.UUID, limit: int = Query(50, ge=1, le=100),
               offset: int = Query(0, ge=0, le=10000), db: Session = Depends(get_session)):
    _case(db, case_id)
    criterion = AnalystCaseNote.case_id == case_id
    total = db.scalar(select(func.count()).select_from(AnalystCaseNote).where(criterion)) or 0
    rows = db.scalars(select(AnalystCaseNote).where(criterion)
                      .order_by(AnalystCaseNote.case_version.desc()).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [CaseNoteOut.model_validate(x) for x in rows]}


@router.get("/{case_id}/notification-preview", response_model=dict)
def notification_preview(case_id: uuid.UUID, db: Session = Depends(get_session)):
    """Only a local safe preview. No destination, transport or scheduling implemented."""
    row = _case(db, case_id)
    return {"enabled": False, "delivery": "DISABLED", "requires_manual_review": True,
            "template": "CASE_STATUS_CHANGE", "case_id": str(row.id),
            "status": row.status, "priority": row.priority, "version": row.version,
            "contents": "METADATA_ONLY", "destinations": []}
