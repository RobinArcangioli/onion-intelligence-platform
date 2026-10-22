"""Cycle de vie, priorisation et audit détaillé des sources.

Revision ID: 0002_source_lifecycle
Revises: 0001_bootstrap
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_source_lifecycle"
down_revision: str | None = "0001_bootstrap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("onion_sources", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("onion_sources", sa.Column("priority", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("onion_sources", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_onion_sources_active_deleted", "onion_sources", ["is_active", "deleted_at"])
    op.add_column("audit_logs", sa.Column("details", sa.Text(), nullable=False, server_default="{}"))
    # Aucun changement rétroactif de l'autorisation existante.
    # La collecte reste désactivée pour les nouvelles sources de lot 1.


def downgrade() -> None:
    op.drop_column("audit_logs", "details")
    op.drop_index("ix_onion_sources_active_deleted", table_name="onion_sources")
    op.drop_column("onion_sources", "deleted_at")
    op.drop_column("onion_sources", "priority")
    op.drop_column("onion_sources", "is_active")
