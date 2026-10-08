"""alertas de empleo por correo

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08 10:00:00

Solo una tabla nueva (sin modo batch): nada que recrear en SQLite.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'alert_inboxes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('forwarding_code', sa.String(length=20), nullable=False),
        sa.Column('forwarding_from', sa.String(length=320), nullable=False),
        sa.Column('last_received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('received_count', sa.Integer(), nullable=False),
        sa.Column('last_summary', sa.Text(), nullable=False),
        sa.Column('quota_day', sa.Date(), nullable=True),
        sa.Column('quota_used', sa.Integer(), nullable=False),
        sa.Column('pending', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_alert_inboxes_user_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_alert_inboxes'),
    )
    op.create_index('uq_alert_inboxes_user_id', 'alert_inboxes', ['user_id'], unique=True)
    op.create_index('uq_alert_inboxes_token', 'alert_inboxes', ['token'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_alert_inboxes_token', table_name='alert_inboxes')
    op.drop_index('uq_alert_inboxes_user_id', table_name='alert_inboxes')
    op.drop_table('alert_inboxes')
