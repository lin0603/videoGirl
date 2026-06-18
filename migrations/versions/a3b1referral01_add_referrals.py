"""add referrals table

Revision ID: a3b1referral01
Revises: f5ad6779c95c
Create Date: 2026-06-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3b1referral01"
down_revision = "f5ad6779c95c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("referred_id", sa.BigInteger(), primary_key=True),
        sa.Column("referrer_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("reward_given_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["referred_id"], ["users.telegram_id"]),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.telegram_id"]),
    )
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"])


def downgrade() -> None:
    op.drop_index("ix_referrals_referrer_id", "referrals")
    op.drop_table("referrals")
