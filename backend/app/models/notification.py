"""M6-C: approved internal-only notification rules and immutable unsent snapshots."""
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CaseNotificationPolicy(Base):
    __tablename__ = "case_notification_policies"
    __table_args__ = (UniqueConstraint("code", name="uq_case_notification_policy_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    target_status: Mapped[str] = mapped_column(String(16), nullable=False)
    minimum_priority: Mapped[str] = mapped_column(String(16), nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CaseNotificationDraft(Base):
    __tablename__ = "case_notification_drafts"
    __table_args__ = (
        UniqueConstraint("policy_id", "case_id", "case_version", name="uq_case_notification_draft_version"),
        Index("ix_case_notification_drafts_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("case_notification_policies.id"), nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("analyst_cases.id"), nullable=False)
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(24), nullable=False, default="NOT_SENT", server_default="NOT_SENT")
    # A bounded, fixed-key payload: no note bodies, source content, destinations or credentials.
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
