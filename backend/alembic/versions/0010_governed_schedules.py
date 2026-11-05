"""Explicit opt-in schedules and a DB-only dispatch audit trail.

Revision ID: 0010_governed_schedules
Revises: 0009_job_leases

No default schedule rows, no automatically enabled source, no network jobs.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_governed_schedules"
down_revision = "0009_job_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_schedules",
        sa.Column("source_id", sa.Uuid(as_uuid=True), sa.ForeignKey("onion_sources.id"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("daily_budget", sa.Integer(), nullable=False),
        sa.Column("window_start_hour", sa.Integer(), nullable=False),
        sa.Column("window_end_hour", sa.Integer(), nullable=False),
        sa.Column("approval_reference", sa.String(500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("interval_minutes BETWEEN 60 AND 10080", name="ck_schedule_interval"),
        sa.CheckConstraint("daily_budget BETWEEN 1 AND 24", name="ck_schedule_budget"),
        sa.CheckConstraint("window_start_hour BETWEEN 0 AND 23", name="ck_schedule_start"),
        sa.CheckConstraint("window_end_hour BETWEEN 1 AND 24", name="ck_schedule_end"),
        sa.CheckConstraint("window_start_hour < window_end_hour", name="ck_schedule_window"),
    )
    op.create_index("ix_source_schedules_due", "source_schedules", ["enabled", "next_run_at"])
    op.create_table(
        "schedule_decisions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.Uuid(as_uuid=True), sa.ForeignKey("onion_sources.id"), nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=True), sa.ForeignKey("crawl_jobs.id"), nullable=True),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("approval_reference", sa.String(500), nullable=False),
        sa.Column("authorization_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_schedule_decisions_source_created", "schedule_decisions", ["source_id", "created_at"])


def downgrade() -> None:
    # OFFLINE ONLY: removes schedule configuration and all its decision history.
    op.drop_index("ix_schedule_decisions_source_created", table_name="schedule_decisions")
    op.drop_table("schedule_decisions")
    op.drop_index("ix_source_schedules_due", table_name="source_schedules")
    op.drop_table("source_schedules")
