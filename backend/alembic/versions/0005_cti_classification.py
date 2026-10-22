"""Heuristic classification and public CTI references.

Revision ID: 0005_cti_classification
Revises: 0004_intelligence
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0005_cti_classification"
down_revision: str | None = "0004_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("classification_results",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("observation_id", sa.Uuid(as_uuid=True), sa.ForeignKey("source_observations.id"), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), sa.ForeignKey("onion_sources.id"), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("evidence_codes", sa.JSON(), nullable=False),
        sa.Column("ruleset_version", sa.String(32), nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("review_reason", sa.String(100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("observation_id", "category", name="uq_classification_observation_category"),
    )
    op.create_index("ix_classification_source_created", "classification_results", ["source_id", "created_at"])
    op.create_index("ix_classification_review", "classification_results", ["review_status", "created_at"])
    op.create_table("threat_indicators",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("observation_id", sa.Uuid(as_uuid=True), sa.ForeignKey("source_observations.id"), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), sa.ForeignKey("onion_sources.id"), nullable=False),
        sa.Column("indicator_type", sa.String(40), nullable=False),
        sa.Column("public_reference", sa.String(32), nullable=False, server_default=""),
        sa.Column("verification_status", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("evidence_codes", sa.JSON(), nullable=False),
        sa.Column("ruleset_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("observation_id", "indicator_type", "public_reference", name="uq_indicator_observation_kind_ref"),
    )
    op.create_index("ix_threat_indicator_source_created", "threat_indicators", ["source_id", "created_at"])
    op.create_index("ix_threat_indicator_type", "threat_indicators", ["indicator_type", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_threat_indicator_type", table_name="threat_indicators")
    op.drop_index("ix_threat_indicator_source_created", table_name="threat_indicators")
    op.drop_table("threat_indicators")
    op.drop_index("ix_classification_review", table_name="classification_results")
    op.drop_index("ix_classification_source_created", table_name="classification_results")
    op.drop_table("classification_results")
