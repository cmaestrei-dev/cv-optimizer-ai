"""avisos de correos que no son alertas

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08 18:00:00

Solo columnas nuevas (add_column, sin recrear la tabla).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('alert_inboxes', sa.Column('ignored_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('alert_inboxes', sa.Column('last_ignored_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('alert_inboxes') as batch:
        batch.drop_column('last_ignored_at')
        batch.drop_column('ignored_count')
