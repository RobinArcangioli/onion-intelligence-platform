"""Collecte Tor contrôlée : jobs, observations sans corps, candidats non visités.

Revision ID: 0003_tor_collection
Revises: 0002_source_lifecycle
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0003_tor_collection"
down_revision: str | None = "0002_source_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crawl_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.Uuid(as_uuid=True), sa.ForeignKey("onion_sources.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_crawl_jobs_source_created", "crawl_jobs", ["source_id", "created_at"])
    op.create_table(
        "source_observations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.Uuid(as_uuid=True), sa.ForeignKey("crawl_jobs.id"), unique=True, nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), sa.ForeignKey("onion_sources.id"), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("response_bytes", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False, server_default=""),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("text_length", sa.Integer(), nullable=False),
        sa.Column("discovered_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_source_observations_source_created", "source_observations", ["source_id", "created_at"])
    op.create_table(
        "discovered_onions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.Uuid(as_uuid=True), sa.ForeignKey("onion_sources.id"), nullable=False),
        sa.Column("target_url", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_discovered_onions_source_target", "discovered_onions", ["source_id", "target_url"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_discovered_onions_source_target", table_name="discovered_onions")
    op.drop_table("discovered_onions")
    op.drop_index("ix_source_observations_source_created", table_name="source_observations")
    op.drop_table("source_observations")
    op.drop_index("ix_crawl_jobs_source_created", table_name="crawl_jobs")
    op.drop_table("crawl_jobs")
