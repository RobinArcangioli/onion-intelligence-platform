"""M6-C governed, LOCAL-ONLY notification drafts and aggregate operational reporting.

There is deliberately NO SMTP, webhook, socket, dispatcher or delivery scheduler.
"""
import csv
import io
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import AnalystCase, AuditLog, CaseNotificationDraft, CaseNotificationPolicy
from app.schemas.notification import DraftOut, DraftRequest, PolicyCreate, PolicyOut, PolicyUpdate
from app.security.api_key import require_role

router = APIRouter(prefix="/api/v1/case-operations", tags=["case-operations"],
                   dependencies=[Depends(require_role("ANALYST"))])
PRIORITIES = {"UNASSESSED": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
STATUSES = ("OPEN", "IN_REVIEW", "ESCALATED", "CLOSED")


def _audit(db: Session, actor: str, action: str, entity_id: uuid.UUID, details: dict) -> None:
    db.add(AuditLog(actor=actor, action=action, entity_type="case_notification",
                    entity_id=entity_id, details=json.dumps(details, sort_keys=True)))


@router.post("/policies", response_model=PolicyOut, status_code=201,
             dependencies=[Depends(require_role("ADMIN"))])
def create_policy(payload: PolicyCreate, db: Session = Depends(get_session)):
    actor = db.info.get("actor", "api_key_operator")
    row = CaseNotificationPolicy(code=payload.code, target_status=payload.target_status,
                                 minimum_priority=payload.minimum_priority, created_by=actor,
                                 updated_by=actor, approved=False, enabled=False)
    db.add(row)
    try:
        db.flush()
        _audit(db, actor, "case_notification.policy_created", row.id,
               {"code": row.code, "enabled": False, "transport": "NONE"})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Policy code already exists") from None
    db.refresh(row)
    return row


@router.get("/policies", response_model=list[PolicyOut])
def list_policies(db: Session = Depends(get_session)):
    # Analyst can select a policy for an explicit local preview; only ADMIN can edit.
    return db.scalars(select(CaseNotificationPolicy).order_by(CaseNotificationPolicy.code).limit(100)).all()


@router.patch("/policies/{policy_id}", response_model=PolicyOut,
              dependencies=[Depends(require_role("ADMIN"))])
def change_policy(policy_id: uuid.UUID, payload: PolicyUpdate, db: Session = Depends(get_session)):
    row = db.get(CaseNotificationPolicy, policy_id)
    if row is None:
        raise HTTPException(404, "Policy not found")
    now = datetime.now(timezone.utc)
    actor = db.info.get("actor", "api_key_operator")
    result = db.execute(update(CaseNotificationPolicy)
                        .where(CaseNotificationPolicy.id == policy_id,
                               CaseNotificationPolicy.version == payload.expected_version)
                        .values(approved=payload.approved, enabled=payload.enabled,
                                updated_by=actor, updated_at=now,
                                version=payload.expected_version + 1)
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Stale policy version; refresh before editing")
    _audit(db, actor, "case_notification.policy_updated", policy_id,
           {"approved": payload.approved, "enabled": payload.enabled, "transport": "NONE"})
    db.commit()
    db.expire(row)
    db.refresh(row)
    return row


@router.post("/drafts", response_model=DraftOut, status_code=201)
def prepare_notification(payload: DraftRequest, db: Session = Depends(get_session)):
    """Explicit one-shot metadata snapshot; no destination, transport or delivery side effect."""
    policy = db.scalar(select(CaseNotificationPolicy)
                       .where(CaseNotificationPolicy.id == payload.policy_id).with_for_update())
    case = db.scalar(select(AnalystCase).where(AnalystCase.id == payload.case_id).with_for_update())
    if policy is None or case is None:
        raise HTTPException(404, "Policy or case not found")
    if case.version != payload.expected_case_version:
        raise HTTPException(409, "Stale case version")
    if not policy.approved or not policy.enabled:
        raise HTTPException(409, "Policy is not approved and enabled")
    if (case.status != policy.target_status or
            PRIORITIES.get(case.priority, -1) < PRIORITIES[policy.minimum_priority]):
        raise HTTPException(409, "Case does not match the notification policy")

    actor = db.info.get("actor", "api_key_operator")
    snapshot = {"template": "CASE_STATUS_METADATA_V1", "case_id": str(case.id),
                "status": case.status, "priority": case.priority, "version": case.version,
                "policy_code": policy.code, "content": "METADATA_ONLY"}
    draft = CaseNotificationDraft(case_id=case.id, policy_id=policy.id,
                                  case_version=case.version, created_by=actor,
                                  delivery_status="NOT_SENT", payload=snapshot)
    db.add(draft)
    try:
        db.flush()
        _audit(db, actor, "case_notification.draft_prepared", draft.id,
               {"case_id": str(case.id), "case_version": case.version,
                "policy_id": str(policy.id), "delivery": "NOT_SENT"})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Draft already prepared for this policy and case version") from None
    db.refresh(draft)
    return draft


@router.get("/drafts", response_model=dict)
def list_drafts(case_id: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=100),
                offset: int = Query(0, ge=0, le=10000), db: Session = Depends(get_session)):
    filters = [] if case_id is None else [CaseNotificationDraft.case_id == case_id]
    count = db.scalar(select(func.count()).select_from(CaseNotificationDraft).where(*filters)) or 0
    rows = db.scalars(select(CaseNotificationDraft).where(*filters)
                      .order_by(CaseNotificationDraft.created_at.desc(), CaseNotificationDraft.id.desc())
                      .offset(offset).limit(limit)).all()
    return {"total": count, "offset": offset, "limit": limit,
            "items": [DraftOut.model_validate(row).model_dump(mode="json") for row in rows]}


def _operational_summary(db: Session) -> dict:
    """Bounded fixed-key counts, never analyst notes, source content or IOC values."""
    grouped = db.execute(select(AnalystCase.status, func.count()).group_by(AnalystCase.status)).all()
    priorities = db.execute(select(AnalystCase.priority, func.count()).group_by(AnalystCase.priority)).all()
    unassigned = db.scalar(select(func.count()).select_from(AnalystCase)
                           .where(AnalystCase.assignee_id.is_(None), AnalystCase.status != "CLOSED")) or 0
    prepared = db.scalar(select(func.count()).select_from(CaseNotificationDraft)) or 0
    by_status = {s: 0 for s in STATUSES}
    by_status.update({name: count for name, count in grouped if name in by_status})
    by_priority = {p: 0 for p in PRIORITIES}
    by_priority.update({name: count for name, count in priorities if name in by_priority})
    return {"report_type": "CASE_OPERATIONS_METADATA_V1", "contents": "AGGREGATED_ONLY",
            "total_cases": sum(by_status.values()), "by_status": by_status,
            "by_priority": by_priority, "open_unassigned": unassigned,
            "notification_drafts": prepared, "notifications_sent": 0,
            "external_transport": "NOT_IMPLEMENTED"}


@router.get("/summary")
def operations_summary(db: Session = Depends(get_session)):
    return _operational_summary(db)


@router.get("/summary/export")
def export_operations(format: str = Query("json", pattern="^(json|csv)$"),
                      db: Session = Depends(get_session)):
    snapshot = _operational_summary(db)
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["category", "key", "count"])
        for section in ("by_status", "by_priority"):
            for key, count in snapshot[section].items():
                writer.writerow([section, key, count])
        for key in ("total_cases", "open_unassigned", "notification_drafts", "notifications_sent"):
            writer.writerow(["aggregate", key, snapshot[key]])
        content, mediatype = buffer.getvalue(), "text/csv; charset=utf-8"
    else:
        content, mediatype = json.dumps(snapshot, sort_keys=True), "application/json"
    return Response(content=content, media_type=mediatype,
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                             "Content-Disposition": f'attachment; filename="oip-case-operations.{format}"'})
