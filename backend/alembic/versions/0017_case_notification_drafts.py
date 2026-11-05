"""M6-C metadata-only internal notification policies and unsent drafts.

Revision ID: 0017_case_notification_drafts
Revises: 0016_case_triage_notes
A downgrade drops policies and drafts; test restoration before any production upgrade.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_case_notification_drafts"
down_revision = "0016_case_triage_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_notification_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("target_status", sa.String(16), nullable=False),
        sa.Column("minimum_priority", sa.String(16), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("updated_by", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_case_notification_policy_code"),
    )
    op.create_table(
        "case_notification_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("policy_id", sa.Uuid(), sa.ForeignKey("case_notification_policies.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("analyst_cases.id"), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("delivery_status", sa.String(24), nullable=False, server_default="NOT_SENT"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("policy_id", "case_id", "case_version", name="uq_case_notification_draft_version"),
    )
    op.create_index("ix_case_notification_drafts_created", "case_notification_drafts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_case_notification_drafts_created", table_name="case_notification_drafts")
    op.drop_table("case_notification_drafts")
    op.drop_table("case_notification_policies")
