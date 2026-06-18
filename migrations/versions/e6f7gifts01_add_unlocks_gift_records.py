"""add unlocks and gift_records tables (task #22)

Revision ID: e6f7gifts01
Revises: d5e6lora01
Create Date: 2026-06-19 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e6f7gifts01"
down_revision = "d5e6lora01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unlocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("item_key", sa.String(256), nullable=False),
        sa.Column("stars_paid", sa.Integer(), nullable=False),
        sa.Column("charge_id", sa.String(256), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("charge_id", name="uq_unlocks_charge_id"),
    )
    op.create_index("ix_unlocks_user_item", "unlocks", ["user_id", "item_key"])

    op.create_table(
        "gift_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=False),
        sa.Column("gift_key", sa.String(128), nullable=False),
        sa.Column("stars_paid", sa.Integer(), nullable=False),
        sa.Column("mood_boost", sa.Float(), nullable=False),
        sa.Column("charge_id", sa.String(256), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sender_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("charge_id", name="uq_gift_records_charge_id"),
    )
    op.create_index("ix_gift_records_sender", "gift_records", ["sender_id", "sent_at"])


def downgrade() -> None:
    op.drop_index("ix_gift_records_sender", "gift_records")
    op.drop_table("gift_records")
    op.drop_index("ix_unlocks_user_item", "unlocks")
    op.drop_table("unlocks")
