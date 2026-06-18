"""add user intimacy fields

Revision ID: 6a1c6a75d2fb
Revises: g8h9gacha01
Create Date: 2026-06-19 07:17:32.409420

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6a1c6a75d2fb'
down_revision: Union[str, Sequence[str], None] = 'g8h9gacha01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('intimacy_level', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('affection_score', sa.Float(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('streak_days', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('last_interaction_date', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'last_interaction_date')
    op.drop_column('users', 'streak_days')
    op.drop_column('users', 'affection_score')
    op.drop_column('users', 'intimacy_level')
