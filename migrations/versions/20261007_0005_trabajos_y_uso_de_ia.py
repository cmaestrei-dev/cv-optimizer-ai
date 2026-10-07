"""trabajos en segundo plano, uso de ia, evidencias y documento del cv

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-07 17:10:00

Sin modo batch: tablas nuevas y columnas agregadas, nada que obligue a recrear tablas en SQLite.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ai_usage',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('calls', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'day'),
    )
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('result', sa.Text(), nullable=False),
        sa.Column('error', sa.Text(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_jobs_status_id', 'jobs', ['status', 'id'])
    op.create_index('ix_jobs_user_id', 'jobs', ['user_id'])
    op.add_column('applications', sa.Column('evidence_json', sa.Text(), server_default='', nullable=False))
    op.add_column('cv_documents', sa.Column('document_json', sa.Text(), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('cv_documents', 'document_json')
    op.drop_column('applications', 'evidence_json')
    op.drop_index('ix_jobs_user_id', table_name='jobs')
    op.drop_index('ix_jobs_status_id', table_name='jobs')
    op.drop_table('jobs')
    op.drop_table('ai_usage')
