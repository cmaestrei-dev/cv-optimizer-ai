"""fecha de publicación y cierre de la vacante

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08 20:00:00

Solo columnas nuevas (add_column, sin recrear la tabla).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('posted_on', sa.Date(), nullable=True))
    op.add_column('applications', sa.Column('closes_on', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('applications') as batch:
        batch.drop_column('closes_on')
        batch.drop_column('posted_on')
