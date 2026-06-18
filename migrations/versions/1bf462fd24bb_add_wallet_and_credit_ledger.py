"""add wallet and credit ledger

Revision ID: 1bf462fd24bb
Revises: 726fd38e4339
Create Date: 2026-06-19 00:03:23.596914

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1bf462fd24bb'
down_revision: Union[str, Sequence[str], None] = '726fd38e4339'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('credit_ledger',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('delta', sa.BigInteger(), nullable=False),
    sa.Column('balance_after', sa.BigInteger(), nullable=False),
    sa.Column('reason', sa.String(length=64), nullable=False),
    sa.Column('reference', sa.String(length=256), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_credit_ledger_user_id'), 'credit_ledger', ['user_id'], unique=False)
    op.create_table('wallets',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('balance', sa.BigInteger(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('wallets')
    op.drop_index(op.f('ix_credit_ledger_user_id'), table_name='credit_ledger')
    op.drop_table('credit_ledger')
