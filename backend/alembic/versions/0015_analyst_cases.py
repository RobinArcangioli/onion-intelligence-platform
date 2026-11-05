"""M6-A: isolated analyst cases and append-only case events.

Revision ID: 0015_analyst_cases
Revises: 0014_ioc_candidates

Only run against a disposable test DB pending PostgreSQL rehearsal and a
verified offsite restore. Downgrade deletes cases/events; never on production.
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_analyst_cases"
down_revision = "0014_ioc_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyst_cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("operators.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("closure_code", sa.String(32), nullable=True),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("alert_id", name="uq_analyst_case_alert"),
    )
    op.create_index("ix_analyst_cases_status_updated", "analyst_cases", ["status", "updated_at"])
    op.create_index("ix_analyst_cases_assignee_updated", "analyst_cases", ["assignee_id", "updated_at"])
    op.create_table(
        "analyst_case_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("analyst_cases.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("assignee_username", sa.String(64), nullable=True),
        sa.Column("reason_code", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("case_id", "version", name="uq_case_event_version"),
    )
    op.create_index("ix_analyst_case_events_case_created", "analyst_case_events", ["case_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_analyst_case_events_case_created", table_name="analyst_case_events")
    op.drop_table("analyst_case_events")
    op.drop_index("ix_analyst_cases_assignee_updated", table_name="analyst_cases")
    op.drop_index("ix_analyst_cases_status_updated", table_name="analyst_cases")
    op.drop_table("analyst_cases")
