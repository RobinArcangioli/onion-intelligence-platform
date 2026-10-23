"""Named operators and revocable authentication tokens.

Revision ID: 0007_named_access
Revises: 0006_alerts_reports
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0007_named_access"
down_revision: str | None = "0006_alerts_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('VIEWER','ANALYST','ADMIN')", name="ck_operators_role"),
    )
    op.create_table(
        "operator_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("operator_id", sa.Uuid(as_uuid=True), sa.ForeignKey("operators.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("label", sa.String(64), nullable=False, server_default="console"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_operator_tokens_operator", "operator_tokens", ["operator_id"])


def downgrade() -> None:
    op.drop_index("ix_operator_tokens_operator", table_name="operator_tokens")
    op.drop_table("operator_tokens")
    op.drop_table("operators")
