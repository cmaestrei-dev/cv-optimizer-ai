"""titular y ciudad del encabezado del CV

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-18 12:00:00

Solo columnas nuevas (add_column, sin recrear la tabla).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('headline', sa.String(), server_default='', nullable=False))
    op.add_column('users', sa.Column('city', sa.String(), server_default='', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_column('city')
        batch.drop_column('headline')
