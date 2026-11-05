"""M6-B: case priorities and controlled internal notes.

Revision ID: 0016_case_triage_notes
Revises: 0015_analyst_cases
Do not run against production without PostgreSQL 17 rehearsal and verified restore.
Downgrade deletes all case notes.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_case_triage_notes"
down_revision = "0015_analyst_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyst_cases", sa.Column("priority", sa.String(16), nullable=False, server_default="UNASSESSED"))
    op.create_table(
        "analyst_case_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("analyst_cases.id"), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("note_code", sa.String(32), nullable=False),
        sa.Column("body", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("case_id", "case_version", name="uq_case_note_version"),
    )
    op.create_index("ix_case_notes_case_created", "analyst_case_notes", ["case_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_case_notes_case_created", table_name="analyst_case_notes")
    op.drop_table("analyst_case_notes")
    op.drop_column("analyst_cases", "priority")
