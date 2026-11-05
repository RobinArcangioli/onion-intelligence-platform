"""Indexes for bounded recent-observation searches and deterministic ordering.

Revision ID: 0012_observation_read_indexes
Revises: 0011_observation_metadata_fts

Transactional migration: adds no columns, deletes no data. Index creation
may hold table locks and consume I/O: review a maintenance window and an
offsite restore before applying on a non-empty PostgreSQL instance.
"""
from alembic import op

revision = "0012_observation_read_indexes"
down_revision = "0011_observation_metadata_fts"
branch_labels = None
depends_on = None


# No CONCURRENTLY here: rollback of a failed transactional migration is safer
# for the isolated rehearsal. Use an explicitly reviewed, online migration for
# large tables after measuring locks and index build time on PostgreSQL 17.
def upgrade() -> None:
    op.execute("CREATE INDEX ix_obs_recent_id_desc "
               "ON source_observations (created_at DESC, id DESC)")
    op.execute("CREATE INDEX ix_obs_source_recent_id_desc "
               "ON source_observations (source_id, created_at DESC, id DESC)")
    op.execute("CREATE INDEX ix_obs_hash_recent_id_desc "
               "ON source_observations (text_sha256, created_at DESC, id DESC)")
    op.execute("CREATE INDEX ix_alerts_observation_id ON alerts (observation_id)")
    op.execute("CREATE INDEX ix_audit_logs_entity_id ON audit_logs (entity_id)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_audit_logs_entity_id")
    op.execute("DROP INDEX ix_alerts_observation_id")
    op.execute("DROP INDEX ix_obs_hash_recent_id_desc")
    op.execute("DROP INDEX ix_obs_source_recent_id_desc")
    op.execute("DROP INDEX ix_obs_recent_id_desc")
