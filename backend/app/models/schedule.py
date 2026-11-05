"""Explicit per-source collection schedules and bounded dispatch decisions."""
import uuid
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, false, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class SourceSchedule(Base):
    __tablename__ = "source_schedules"
    __table_args__ = (
        CheckConstraint("interval_minutes BETWEEN 60 AND 10080", name="ck_schedule_interval"),
        CheckConstraint("daily_budget BETWEEN 1 AND 24", name="ck_schedule_budget"),
        CheckConstraint("window_start_hour BETWEEN 0 AND 23", name="ck_schedule_start"),
        CheckConstraint("window_end_hour BETWEEN 1 AND 24", name="ck_schedule_end"),
        CheckConstraint("window_start_hour < window_end_hour", name="ck_schedule_window"),
        Index("ix_source_schedules_due", "enabled", "next_run_at"),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("onion_sources.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    window_end_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    next_run_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ScheduleDecision(Base):
    __tablename__ = "schedule_decisions"
    __table_args__ = (Index("ix_schedule_decisions_source_created", "source_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("onion_sources.id"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("crawl_jobs.id"), nullable=True)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    authorization_expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
