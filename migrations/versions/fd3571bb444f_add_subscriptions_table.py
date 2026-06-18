"""add subscriptions table

Revision ID: fd3571bb444f
Revises: 9f2a1b7c8d3e
Create Date: 2026-06-18 23:17:30.915638

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fd3571bb444f'
down_revision: Union[str, Sequence[str], None] = '9f2a1b7c8d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('subscriptions',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('grace_period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('telegram_payment_charge_id', sa.String(length=256), nullable=True),
    sa.Column('provider_payment_charge_id', sa.String(length=256), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'status', name='uq_subscriptions_user_id_status')
    )
    op.create_index(op.f('ix_subscriptions_telegram_payment_charge_id'), 'subscriptions', ['telegram_payment_charge_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_subscriptions_user_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_telegram_payment_charge_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
