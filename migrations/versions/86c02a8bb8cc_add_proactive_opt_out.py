"""add proactive opt out

Revision ID: 86c02a8bb8cc
Revises: 1bf462fd24bb
Create Date: 2026-06-19 00:23:05.529025

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '86c02a8bb8cc'
down_revision: Union[str, Sequence[str], None] = '1bf462fd24bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('proactive_opt_out', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'proactive_opt_out')
