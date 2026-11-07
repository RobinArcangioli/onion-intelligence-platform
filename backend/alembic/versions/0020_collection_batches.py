"""Track the set of jobs admitted by a single manual collection."""
from alembic import op
import sqlalchemy as sa

revision = "0020_collection_batches"
down_revision = "0019_source_pages"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("crawl_jobs", sa.Column("batch_id", sa.Uuid()))
    op.create_index("ix_crawl_jobs_batch", "crawl_jobs", ["batch_id"])


def downgrade():
    op.drop_index("ix_crawl_jobs_batch", table_name="crawl_jobs")
    op.drop_column("crawl_jobs", "batch_id")
