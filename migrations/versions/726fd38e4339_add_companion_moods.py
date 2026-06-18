"""add companion moods

Revision ID: 726fd38e4339
Revises: fd3571bb444f
Create Date: 2026-06-18 23:50:47.867478

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '726fd38e4339'
down_revision: Union[str, Sequence[str], None] = 'fd3571bb444f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('companion_moods',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('persona_slug', sa.String(length=64), nullable=False),
    sa.Column('affection', sa.Float(), nullable=False),
    sa.Column('longing', sa.Float(), nullable=False),
    sa.Column('playfulness', sa.Float(), nullable=False),
    sa.Column('upset', sa.Float(), nullable=False),
    sa.Column('last_interaction_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'persona_slug', name='uq_companion_moods_user_persona')
    )
    op.create_index(op.f('ix_companion_moods_persona_slug'), 'companion_moods', ['persona_slug'], unique=False)
    op.create_index(op.f('ix_companion_moods_user_id'), 'companion_moods', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_companion_moods_user_id'), table_name='companion_moods')
    op.drop_index(op.f('ix_companion_moods_persona_slug'), table_name='companion_moods')
    op.drop_table('companion_moods')
