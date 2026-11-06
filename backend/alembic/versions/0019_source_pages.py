"""Add the flat page registry and per-page collection provenance."""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0019_source_pages"
down_revision = "0018_public_report_publications"
branch_labels = None
depends_on = None


def upgrade():
    pages = op.create_table(
        "source_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("onion_sources.id"), nullable=False),
        sa.Column("url", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("source_id", "url", name="uq_source_page_url"),
    )
    for table in ("crawl_jobs", "source_observations"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("page_id", sa.Uuid()))
            batch.create_foreign_key(f"fk_{table}_page", "source_pages", ["page_id"], ["id"])
    op.add_column("source_observations", sa.Column("origin", sa.String(20), nullable=False, server_default="TOR_HTTP"))
    op.create_index("ix_crawl_jobs_waiting", "crawl_jobs", ["status", "source_id", "created_at"])
    op.create_index("ix_obs_page_recent", "source_observations", ["page_id", sa.text("created_at DESC")])
    conn = op.get_bind()
    sources = sa.table("onion_sources", sa.column("id", sa.Uuid()), sa.column("canonical_url", sa.String()))
    for source_id, url in conn.execute(sa.select(sources.c.id, sources.c.canonical_url)):
        conn.execute(pages.insert().values(id=uuid.uuid4(), source_id=source_id, url=url))
    # Historic records keep their original source-level identity. The analysis
    # engine includes them when comparing the migrated legacy address.


def downgrade():
    op.get_bind().execute(sa.text("UPDATE crawl_jobs SET status = 'FAILED', error_code = 'PAGE_QUEUE_REMOVED', "
                                  "finished_at = CURRENT_TIMESTAMP WHERE status = 'WAITING'"))
    op.drop_index("ix_obs_page_recent", table_name="source_observations")
    op.drop_index("ix_crawl_jobs_waiting", table_name="crawl_jobs")
    op.drop_column("source_observations", "origin")
    for table in ("source_observations", "crawl_jobs"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_page", type_="foreignkey")
            batch.drop_column("page_id")
    op.drop_table("source_pages")
