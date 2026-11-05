"""ADMIN-only preview, publication and withdrawal. Existing reports stay internal."""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import AuditLog, Report, ReportPublication
from app.public_view.projections import payload_digest, project_report
from app.security.api_key import require_api_key, require_role

router = APIRouter(prefix='/api/v1/reports', tags=['report-publication'],
                   dependencies=[Depends(require_api_key), Depends(require_role('ADMIN'))])


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_digest: str = Field(pattern='^[0-9a-f]{64}$')


def locked_report(db, report_id):
    row = db.scalar(select(Report).where(Report.id == report_id).with_for_update())
    if row is None:
        raise HTTPException(404, 'Report not found')
    return row


def public_payload(row):
    try:
        return project_report(row)
    except (ValidationError, AttributeError, TypeError):
        raise HTTPException(409, 'Report counters cannot be published') from None


@router.get('/{report_id}/publication-preview')
def preview(report_id: uuid.UUID, db: Session = Depends(get_session)):
    row = db.get(Report, report_id)
    if row is None:
        raise HTTPException(404, 'Report not found')
    payload = public_payload(row)
    current = db.scalar(select(ReportPublication).where(ReportPublication.report_id == report_id,
                                                       ReportPublication.is_public.is_(True)))
    return {'content': payload, 'digest': payload_digest(payload),
            'publication_id': current.id if current else None}


@router.post('/{report_id}/publication', status_code=201)
def publish(report_id: uuid.UUID, request: PublishRequest, db: Session = Depends(get_session)):
    report = locked_report(db, report_id)
    payload = public_payload(report)
    if request.expected_digest != payload_digest(payload):
        raise HTTPException(409, 'Preview changed; review it again')
    if db.scalar(select(ReportPublication.id).where(ReportPublication.report_id == report_id,
                                                   ReportPublication.is_public.is_(True))):
        raise HTTPException(409, 'Report already public')
    row = ReportPublication(report_id=report_id, payload=payload.model_dump(mode='json'),
                            published_by=db.info['actor'])
    db.add(row)
    try:
        db.flush()
        db.add(AuditLog(actor=db.info['actor'], action='report.publish', entity_type='report',
                        entity_id=report_id, details=json.dumps({'publication_id': str(row.id)})))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Report already public') from None
    return {'publication_id': row.id}


@router.delete('/{report_id}/publication/{publication_id}', status_code=204)
def withdraw(report_id: uuid.UUID, publication_id: uuid.UUID, db: Session = Depends(get_session)):
    locked_report(db, report_id)
    row = db.scalar(select(ReportPublication).where(ReportPublication.id == publication_id,
                                                   ReportPublication.report_id == report_id,
                                                   ReportPublication.is_public.is_(True)).with_for_update())
    if row is None:
        raise HTTPException(404, 'Public report not found')
    row.is_public = False
    row.withdrawn_at = datetime.now(timezone.utc)
    db.add(AuditLog(actor=db.info['actor'], action='report.unpublish', entity_type='report',
                    entity_id=report_id, details=json.dumps({'publication_id': str(row.id)})))
    db.commit()
