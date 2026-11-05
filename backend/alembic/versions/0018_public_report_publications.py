"""Add explicit public report versions; existing reports remain private.

Revision ID: 0018_public_report_publications
Revises: 0017_case_notification_drafts
"""
from alembic import op
import sqlalchemy as sa

revision = '0018_public_report_publications'
down_revision = '0017_case_notification_drafts'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('report_publications',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('report_id', sa.Uuid(), sa.ForeignKey('reports.id'), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('published_by', sa.String(80), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_report_publications_recent', 'report_publications', ['published_at', 'id'])
    op.create_index('uq_report_publications_active', 'report_publications', ['report_id'], unique=True,
                    postgresql_where=sa.text('is_public = true'), sqlite_where=sa.text('is_public = 1'))


def downgrade():
    op.drop_index('uq_report_publications_active', table_name='report_publications')
    op.drop_index('ix_report_publications_recent', table_name='report_publications')
    op.drop_table('report_publications')
