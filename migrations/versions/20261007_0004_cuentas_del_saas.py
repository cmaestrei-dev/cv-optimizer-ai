"""cuentas del saas

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-07 15:25:46.851111

Sin modo batch a propósito: en SQLite, agregar una restricción única recrea la tabla `users`, y al
borrar la vieja se borrarían en cascada experiencias, habilidades y postulaciones. Un índice único
logra lo mismo sin recrear nada.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('auth_subject', sa.String(), nullable=True))
    op.create_index('uq_users_auth_subject', 'users', ['auth_subject'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_users_auth_subject', table_name='users')
    op.drop_column('users', 'auth_subject')
