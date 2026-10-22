"""Create immutable reports and deduplicated alerts.

Revision ID: 0006_alerts_reports
Revises: 0005_cti_classification
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0006_alerts_reports"
down_revision: str | None = "0005_cti_classification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("alerts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.Uuid(as_uuid=True), sa.ForeignKey("onion_sources.id"), nullable=False),
        sa.Column("observation_id", sa.Uuid(as_uuid=True), sa.ForeignKey("source_observations.id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("signal_code", sa.String(64), nullable=False),
        sa.Column("priority", sa.String(12), nullable=False),
        sa.Column("verification_status", sa.String(40), nullable=False),
        sa.Column("relevance_score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("reason", sa.String(100), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fingerprint", name="uq_alert_fingerprint"),
    )
    op.create_index("ix_alerts_status_created", "alerts", ["status", "created_at"])
    op.create_index("ix_alerts_source_created", "alerts", ["source_id", "created_at"])
    op.create_table("reports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.Uuid(as_uuid=True), sa.ForeignKey("onion_sources.id"), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reports_created", "reports", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_reports_created", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_alerts_source_created", table_name="alerts")
    op.drop_index("ix_alerts_status_created", table_name="alerts")
    op.drop_table("alerts")
