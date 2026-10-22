"""Registre des sources autorisées : l'état collecte reste désactivé au lot 1."""
import uuid

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, Uuid, false, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OnionSource(Base):
    __tablename__ = "onion_sources"
    __table_args__ = (Index("ix_onion_sources_active_deleted", "is_active", "deleted_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_url: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="UNKNOWN", server_default="UNKNOWN", nullable=False, index=True)
    availability_status: Mapped[str] = mapped_column(String(40), default="NOT_CHECKED", server_default="NOT_CHECKED", nullable=False)
    authorization_note: Mapped[str] = mapped_column(Text, nullable=False)
    approved_for_collection: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    collection_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    deleted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
