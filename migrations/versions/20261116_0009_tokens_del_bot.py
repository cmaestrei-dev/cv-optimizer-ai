"""tokens del bot local (solo su huella)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-16 18:00:00

Tabla nueva: no recrea ninguna existente.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'bot_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=60), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('hint', sa.String(length=8), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_bot_tokens_user_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_bot_tokens'),
    )
    op.create_index('ix_bot_tokens_user_id', 'bot_tokens', ['user_id'], unique=False)
    op.create_index('uq_bot_tokens_token_hash', 'bot_tokens', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_bot_tokens_token_hash', table_name='bot_tokens')
    op.drop_index('ix_bot_tokens_user_id', table_name='bot_tokens')
    op.drop_table('bot_tokens')
