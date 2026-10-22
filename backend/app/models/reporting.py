"""Minimal immutable findings snapshots and actionable alert records."""
import uuid

from sqlalchemy import (DateTime, ForeignKey, Index, Integer, JSON, String,
                        Uuid, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_alert_fingerprint"),
        Index("ix_alerts_status_created", "status", "created_at"),
        Index("ix_alerts_source_created", "source_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("onion_sources.id"), nullable=False)
    observation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("source_observations.id"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    signal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(12), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False)
    relevance_score: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", server_default="OPEN")
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    acknowledged_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_created", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("onion_sources.id"), nullable=True)
    period_start: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    # Snapshot only of sanitized counters, codes, UUIDs and public verification statuses.
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
