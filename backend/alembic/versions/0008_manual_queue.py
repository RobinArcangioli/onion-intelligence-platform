"""Manual collection queue: one pending/running job per approved source.

Revision ID: 0008_manual_queue
Revises: 0007_named_access
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0008_manual_queue"
down_revision: str | None = "0007_named_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_crawl_jobs_active_source", "crawl_jobs", ["source_id"], unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'RUNNING')"),
        sqlite_where=sa.text("status IN ('PENDING', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_crawl_jobs_active_source", table_name="crawl_jobs")
