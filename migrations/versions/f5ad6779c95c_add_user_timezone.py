"""add user timezone

Revision ID: f5ad6779c95c
Revises: 06ad8c57795e
Create Date: 2026-06-19 00:27:24.152328

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f5ad6779c95c'
down_revision: Union[str, Sequence[str], None] = '06ad8c57795e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('timezone', sa.String(length=64), nullable=False, server_default='Asia/Taipei'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'timezone')
