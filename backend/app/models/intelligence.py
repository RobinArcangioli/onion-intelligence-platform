"""Minimal watchlists and match counters: never store page extracts or contexts."""
import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Uuid, UniqueConstraint, false, func, true
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WatchlistRule(Base):
    __tablename__ = "watchlist_rules"
    __table_args__ = (UniqueConstraint("watchlist_id", "phrase_normalized", name="uq_rule_watchlist_phrase"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("watchlists.id"), nullable=False, index=True)
    phrase: Mapped[str] = mapped_column(String(120), nullable=False)
    phrase_normalized: Mapped[str] = mapped_column(String(160), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default="10")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class KeywordMatch(Base):
    __tablename__ = "keyword_matches"
    __table_args__ = (UniqueConstraint("observation_id", "rule_id", name="uq_match_observation_rule"),
                      Index("ix_matches_observation", "observation_id"))

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    observation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("source_observations.id"), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("watchlist_rules.id"), nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False)
    contribution: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
