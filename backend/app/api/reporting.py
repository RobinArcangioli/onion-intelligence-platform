"""Authenticated alerts and on-demand, immutable metadata-only reports."""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import Alert, AuditLog, OnionSource, Report
from app.reports.builder import build_snapshot, export_csv
from app.schemas.reporting import AlertOut, AlertReview, ReportCreate, ReportOut
from app.security.api_key import require_api_key, require_role

router = APIRouter(prefix="/api/v1", tags=["alerts-reports"], dependencies=[Depends(require_api_key)])


@router.get("/alerts")
def list_alerts(source_id: uuid.UUID | None = None,
                status: str | None = Query(None, pattern="^(OPEN|ACKNOWLEDGED|RESOLVED)$"),
                event_type: str | None = Query(None, min_length=2, max_length=40),
                priority: str | None = Query(None, pattern="^(LOW|MEDIUM|HIGH)$"),
                limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                db: Session = Depends(get_session)) -> dict:
    conditions = []
    if source_id is not None:
        conditions.append(Alert.source_id == source_id)
    if status is not None:
        conditions.append(Alert.status == status)
    if event_type is not None:
        conditions.append(Alert.event_type == event_type)
    if priority is not None:
        conditions.append(Alert.priority == priority)
    total = db.scalar(select(func.count()).select_from(Alert).where(*conditions)) or 0
    rows = db.scalars(select(Alert).where(*conditions)
                      .order_by(Alert.created_at.desc(), Alert.id.desc())
                      .limit(limit).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [AlertOut.model_validate(row) for row in rows]}


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: uuid.UUID, db: Session = Depends(get_session)) -> Alert:
    row = db.get(Alert, alert_id)
    if row is None:
        raise HTTPException(404, "Alert not found")
    return row


@router.patch("/alerts/{alert_id}", response_model=AlertOut, dependencies=[Depends(require_role("ANALYST"))])
def review_alert(alert_id: uuid.UUID, payload: AlertReview,
                 db: Session = Depends(get_session)) -> Alert:
    row = db.scalar(select(Alert).where(Alert.id == alert_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Alert not found")
    valid = (row.status == "OPEN" and payload.status in ("ACKNOWLEDGED", "RESOLVED")) or (
        row.status == "ACKNOWLEDGED" and payload.status == "RESOLVED")
    if not valid:
        raise HTTPException(409, "Invalid alert transition")
    row.status = payload.status
    row.reason = payload.reason
    now = datetime.now(timezone.utc)
    if payload.status == "ACKNOWLEDGED":
        row.acknowledged_at = now
    else:
        row.resolved_at = now
    db.add(AuditLog(actor=db.info.get("actor", "api_key_operator"), action="alert.review", entity_type="alert",
                    entity_id=row.id, details=json.dumps({"status": payload.status, "reason": payload.reason})))
    db.commit()
    db.refresh(row)
    return row


@router.post("/reports", response_model=ReportOut, status_code=201, dependencies=[Depends(require_role("ANALYST"))])
def create_report(payload: ReportCreate, db: Session = Depends(get_session)) -> Report:
    if payload.source_id is not None and db.get(OnionSource, payload.source_id) is None:
        raise HTTPException(404, "Source not found")
    # Explicitly metadata-only, bounded snapshot at the instant of creation.
    snapshot = build_snapshot(db, start=payload.period_start, end=payload.period_end,
                              source_id=payload.source_id, max_rows=payload.max_rows_per_type)
    row = Report(source_id=payload.source_id, period_start=payload.period_start,
                 period_end=payload.period_end, snapshot=snapshot)
    db.add(row)
    db.flush()
    db.add(AuditLog(actor=db.info.get("actor", "api_key_operator"), action="report.create", entity_type="report",
                    entity_id=row.id, details="{}"))
    db.commit()
    db.refresh(row)
    return row


@router.get("/reports")
def list_reports(source_id: uuid.UUID | None = None,
                 limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_session)) -> dict:
    where = [] if source_id is None else [Report.source_id == source_id]
    total = db.scalar(select(func.count()).select_from(Report).where(*where)) or 0
    rows = db.scalars(select(Report).where(*where)
                      .order_by(Report.created_at.desc(), Report.id.desc())
                      .limit(limit).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [ReportOut.model_validate(row) for row in rows]}


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: uuid.UUID, db: Session = Depends(get_session)) -> Report:
    row = db.get(Report, report_id)
    if row is None:
        raise HTTPException(404, "Report not found")
    return row


@router.get("/reports/{report_id}/export")
def download_report(report_id: uuid.UUID,
                    format: str = Query("json", pattern="^(json|csv)$"),
                    db: Session = Depends(get_session)) -> Response:
    row = db.get(Report, report_id)
    if row is None:
        raise HTTPException(404, "Report not found")
    # Snapshot is persisted and never re-queried for export.
    if format == "csv":
        body = export_csv(row.snapshot)
        media_type = "text/csv; charset=utf-8"
    else:
        body = json.dumps(jsonable_encoder({"report_id": row.id, **row.snapshot}),
                          ensure_ascii=False, sort_keys=True)
        media_type = "application/json"
    return Response(content=body, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="oip-report-{report_id}.{format}"',
                             "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
