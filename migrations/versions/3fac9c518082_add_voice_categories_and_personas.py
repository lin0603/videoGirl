"""add voice categories and personas

Revision ID: 3fac9c518082
Revises: c7a1voicecat01
Create Date: 2026-06-18 16:32:11.604464

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3fac9c518082'
down_revision: Union[str, Sequence[str], None] = 'c7a1voicecat01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('personas',
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('avatar_url', sa.String(length=1024), nullable=True),
    sa.Column('system_prompt', sa.Text(), nullable=False),
    sa.Column('greeting', sa.Text(), nullable=False),
    sa.Column('nsfw_level', sa.BigInteger(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('slug')
    )
    op.create_table('voice_categories',
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('sort_order', sa.BigInteger(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('slug')
    )
    op.add_column('voices', sa.Column('sort_order', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('voices', sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')))
    op.add_column('voices', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')))
    op.add_column('voices', sa.Column('category_slug', sa.String(length=64), nullable=True))
    op.create_foreign_key(None, 'voices', 'voice_categories', ['category_slug'], ['slug'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, 'voices', type_='foreignkey')
    op.drop_column('voices', 'category_slug')
    op.drop_column('voices', 'updated_at')
    op.drop_column('voices', 'created_at')
    op.drop_column('voices', 'sort_order')
    op.drop_table('voice_categories')
    op.drop_table('personas')
