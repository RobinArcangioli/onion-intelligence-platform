"""Fenced leases for manually queued collection jobs.

Revision ID: 0009_job_leases
Revises: 0008_manual_queue

No existing job is automatically rescheduled or changed. Legacy RUNNING jobs
remain visible to the operator-only stale reconciliation command.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009_job_leases"
down_revision: str | None = "0008_manual_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("crawl_jobs", sa.Column("lease_token", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("crawl_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("crawl_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_crawl_jobs_running_lease", "crawl_jobs", ["status", "lease_expires_at"])


def downgrade() -> None:
    # Only when all queue workers are stopped and no RUNNING jobs exist.
    op.drop_index("ix_crawl_jobs_running_lease", table_name="crawl_jobs")
    op.drop_column("crawl_jobs", "heartbeat_at")
    op.drop_column("crawl_jobs", "lease_expires_at")
    op.drop_column("crawl_jobs", "lease_token")
