"""Non-sensitive CTI derivatives; no stored text excerpts or private IOCs."""
import uuid
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ClassificationResult(Base):
    __tablename__ = "classification_results"
    __table_args__ = (
        UniqueConstraint("observation_id", "category", name="uq_classification_observation_category"),
        Index("ix_classification_source_created", "source_id", "created_at"),
        Index("ix_classification_review", "review_status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    observation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("source_observations.id"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("onion_sources.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_codes: Mapped[list] = mapped_column(JSON, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False)
    review_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ThreatIndicator(Base):
    __tablename__ = "threat_indicators"
    __table_args__ = (
        UniqueConstraint("observation_id", "indicator_type", "public_reference", name="uq_indicator_observation_kind_ref"),
        Index("ix_threat_indicator_source_created", "source_id", "created_at"),
        Index("ix_threat_indicator_type", "indicator_type", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    observation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("source_observations.id"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("onion_sources.id"), nullable=False)
    indicator_type: Mapped[str] = mapped_column(String(40), nullable=False)
    public_reference: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_codes: Mapped[list] = mapped_column(JSON, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
