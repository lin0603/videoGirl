"""enable pgvector

Revision ID: 12028d6d28fa
Revises: 
Create Date: 2026-06-18 10:33:38.590902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12028d6d28fa'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable the pgvector extension."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")


def downgrade() -> None:
    """Disable the pgvector extension."""
    op.execute("DROP EXTENSION IF EXISTS vector;")
