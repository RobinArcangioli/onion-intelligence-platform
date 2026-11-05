"""Add analyst triage to public CTI references, keeping existing candidates unreviewed.

Revision ID: 0013_indicator_triage
Revises: 0012_observation_read_indexes

No migration on OVH without a verified offsite restoration; index creation
can acquire locks. Downgrade discards triage fields, so use only on a test DB.
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_indicator_triage"
down_revision = "0012_observation_read_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("threat_indicators", sa.Column("review_status", sa.String(24), nullable=False, server_default="PENDING"))
    op.add_column("threat_indicators", sa.Column("analyst_priority", sa.String(16), nullable=False, server_default="UNASSESSED"))
    op.add_column("threat_indicators", sa.Column("review_reason", sa.String(100), nullable=True))
    op.add_column("threat_indicators", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_indicator_reference_review", "threat_indicators", ["indicator_type", "public_reference", "review_status"])


def downgrade() -> None:
    op.drop_index("ix_indicator_reference_review", table_name="threat_indicators")
    op.drop_column("threat_indicators", "reviewed_at")
    op.drop_column("threat_indicators", "review_reason")
    op.drop_column("threat_indicators", "analyst_priority")
    op.drop_column("threat_indicators", "review_status")
