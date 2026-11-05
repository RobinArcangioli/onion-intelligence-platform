"""Metadata-only FTS index for the observation investigator view.

Revision ID: 0011_observation_metadata_fts
Revises: 0010_governed_schedules

No schema change to stored observations, no table rewrite, no data purge.
Non-PostgreSQL test databases use a bounded substring search fallback.
"""
from alembic import op

revision = "0011_observation_metadata_fts"
down_revision = "0010_governed_schedules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # Building this index on production can still acquire locks and create
        # I/O load. Upgrade only during a reviewed maintenance window.
        op.execute("""CREATE INDEX ix_observation_metadata_search
            ON source_observations USING GIN
            (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(description, '')))""")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX ix_observation_metadata_search")
