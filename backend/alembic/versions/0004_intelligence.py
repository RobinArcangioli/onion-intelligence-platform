"""Ephemeral keyword analysis, bounded scoring, discovery review.

Revision ID: 0004_intelligence
Revises: 0003_tor_collection
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0004_intelligence"
down_revision: str | None = "0003_tor_collection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source_observations", sa.Column("change_status", sa.String(20), nullable=False, server_default="UNKNOWN"))
    op.add_column("source_observations", sa.Column("relevance_score", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("source_observations", sa.Column("keyword_hits", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("discovered_onions", sa.Column("evidence_kind", sa.String(16), nullable=False, server_default="LINK"))
    op.add_column("discovered_onions", sa.Column("review_reason", sa.String(100), nullable=True))
    op.add_column("discovered_onions", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("watchlists",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table("watchlist_rules",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("watchlist_id", sa.Uuid(as_uuid=True), sa.ForeignKey("watchlists.id"), nullable=False),
        sa.Column("phrase", sa.String(120), nullable=False),
        sa.Column("phrase_normalized", sa.String(160), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("watchlist_id", "phrase_normalized", name="uq_rule_watchlist_phrase"),
    )
    op.create_index("ix_watchlist_rules_watchlist_id", "watchlist_rules", ["watchlist_id"])
    op.create_table("keyword_matches",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("observation_id", sa.Uuid(as_uuid=True), sa.ForeignKey("source_observations.id"), nullable=False),
        sa.Column("rule_id", sa.Uuid(as_uuid=True), sa.ForeignKey("watchlist_rules.id"), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("contribution", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("observation_id", "rule_id", name="uq_match_observation_rule"),
    )
    op.create_index("ix_matches_observation", "keyword_matches", ["observation_id"])


def downgrade() -> None:
    op.drop_index("ix_matches_observation", table_name="keyword_matches")
    op.drop_table("keyword_matches")
    op.drop_index("ix_watchlist_rules_watchlist_id", table_name="watchlist_rules")
    op.drop_table("watchlist_rules")
    op.drop_table("watchlists")
    op.drop_column("discovered_onions", "reviewed_at")
    op.drop_column("discovered_onions", "review_reason")
    op.drop_column("discovered_onions", "evidence_kind")
    op.drop_column("source_observations", "change_status")
    op.drop_column("source_observations", "keyword_hits")
    op.drop_column("source_observations", "relevance_score")
