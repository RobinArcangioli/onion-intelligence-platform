"""M5-B: independent, opt-in, reviewable IOC mentions; no old data rewritten.

Revision ID: 0014_ioc_candidates
Revises: 0013_indicator_triage

Production migration remains blocked pending PostgreSQL rehearsal and a
verified offsite restore. Downgrade removes IOC review records; test only.
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_ioc_candidates"
down_revision = "0013_indicator_triage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ioc_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("observation_id", sa.Uuid(), sa.ForeignKey("source_observations.id"), nullable=False),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("onion_sources.id"), nullable=False),
        sa.Column("indicator_type", sa.String(16), nullable=False),
        sa.Column("normalized_value", sa.String(253), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("evidence_codes", sa.JSON(), nullable=False),
        sa.Column("ruleset_version", sa.String(40), nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("analyst_priority", sa.String(16), nullable=False, server_default="UNASSESSED"),
        sa.Column("review_reason", sa.String(100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("observation_id", "indicator_type", "normalized_value",
                            name="uq_ioc_candidate_observation_type_value"),
    )
    op.create_index("ix_ioc_candidate_source_created", "ioc_candidates", ["source_id", "created_at"])
    op.create_index("ix_ioc_candidate_review", "ioc_candidates", ["review_status", "created_at"])
    op.create_index("ix_ioc_candidate_type_value_review", "ioc_candidates",
                    ["indicator_type", "normalized_value", "review_status"])


def downgrade() -> None:
    op.drop_index("ix_ioc_candidate_type_value_review", table_name="ioc_candidates")
    op.drop_index("ix_ioc_candidate_review", table_name="ioc_candidates")
    op.drop_index("ix_ioc_candidate_source_created", table_name="ioc_candidates")
    op.drop_table("ioc_candidates")
