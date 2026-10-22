"""Observations minimales : jamais de corps HTML, de médias ni de secrets."""
import uuid
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (Index("ix_crawl_jobs_source_created", "source_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("onion_sources.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", server_default="PENDING")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SourceObservation(Base):
    __tablename__ = "source_observations"
    __table_args__ = (Index("ix_source_observations_source_created", "source_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("crawl_jobs.id"), unique=True, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("onion_sources.id"), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    response_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False, default="", server_default="")
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="")
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    text_length: Mapped[int] = mapped_column(Integer, nullable=False)
    discovered_links: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DiscoveredOnion(Base):
    __tablename__ = "discovered_onions"
    __table_args__ = (
        Index("ix_discovered_onions_source_target", "source_id", "target_url", unique=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("onion_sources.id"), nullable=False)
    target_url: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", server_default="PENDING")
    first_seen_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
