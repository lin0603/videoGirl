"""add payment transactions

Revision ID: 9f2a1b7c8d3e
Revises: 8d0c1b2a3f4e
Create Date: 2026-06-18 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f2a1b7c8d3e"
down_revision: Union[str, Sequence[str], None] = "8d0c1b2a3f4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.String(length=128), nullable=False),
        sa.Column("product", sa.String(length=64), nullable=False),
        sa.Column("amount_stars", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="invoice_created",
        ),
        sa.Column("telegram_payment_charge_id", sa.String(length=256), nullable=True),
        sa.Column("provider_payment_charge_id", sa.String(length=256), nullable=True),
        sa.Column("invoice_link", sa.String(length=2048), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payload", name="uq_payment_transactions_payload"),
        sa.UniqueConstraint(
            "telegram_payment_charge_id",
            name="uq_payment_transactions_telegram_charge_id",
        ),
    )
    op.create_index(
        op.f("ix_payment_transactions_user_id"),
        "payment_transactions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_transactions_telegram_payment_charge_id"),
        "payment_transactions",
        ["telegram_payment_charge_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_payment_transactions_telegram_payment_charge_id"),
        table_name="payment_transactions",
    )
    op.drop_index(op.f("ix_payment_transactions_user_id"), table_name="payment_transactions")
    op.drop_table("payment_transactions")
