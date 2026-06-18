"""add last proactive at to mood

Revision ID: 06ad8c57795e
Revises: 86c02a8bb8cc
Create Date: 2026-06-19 00:23:45.516858

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '06ad8c57795e'
down_revision: Union[str, Sequence[str], None] = '86c02a8bb8cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('companion_moods', sa.Column('last_proactive_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('companion_moods', 'last_proactive_at')
