"""Immutable public report version; withdrawal never edits its content."""
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid, func, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReportPublication(Base):
    __tablename__ = 'report_publications'
    __table_args__ = (
        Index('ix_report_publications_recent', 'published_at', 'id'),
        Index('uq_report_publications_active', 'report_id', unique=True,
              postgresql_where=text('is_public = true'), sqlite_where=text('is_public = 1')),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('reports.id'), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    published_by: Mapped[str] = mapped_column(String(80), nullable=False)
    published_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    withdrawn_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
