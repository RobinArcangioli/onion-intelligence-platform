"""Analyst case workflow: metadata-only, separate from alert's own lifecycle."""
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalystCase(Base):
    __tablename__ = "analyst_cases"
    __table_args__ = (
        UniqueConstraint("alert_id", name="uq_analyst_case_alert"),
        Index("ix_analyst_cases_status_updated", "status", "updated_at"),
        Index("ix_analyst_cases_assignee_updated", "assignee_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("alerts.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN", server_default="OPEN")
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("operators.id"), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="UNASSESSED", server_default="UNASSESSED")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    closure_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalystCaseEvent(Base):
    __tablename__ = "analyst_case_events"
    __table_args__ = (Index("ix_analyst_case_events_case_created", "case_id", "created_at"),
                      UniqueConstraint("case_id", "version", name="uq_case_event_version"))

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("analyst_cases.id"), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="UNASSESSED", server_default="UNASSESSED")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    assignee_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AnalystCaseNote(Base):
    """Short internal notes. Note bodies are NOT copied into AuditLog or external notifications."""
    __tablename__ = "analyst_case_notes"
    __table_args__ = (
        Index("ix_case_notes_case_created", "case_id", "created_at"),
        UniqueConstraint("case_id", "case_version", name="uq_case_note_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("analyst_cases.id"), nullable=False)
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    note_code: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
