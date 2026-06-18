"""add gacha_draws table (task #25)

Revision ID: g8h9gacha01
Revises: f7g8persona01
Create Date: 2026-06-19 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "g8h9gacha01"
down_revision = "f7g8persona01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gacha_draws",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("rarity", sa.String(8), nullable=False),
        sa.Column("scene_key", sa.String(128), nullable=False),
        sa.Column("job_id", sa.String(256), nullable=True),
        sa.Column("cost_credits", sa.Integer(), nullable=False),
        sa.Column("pity_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drawn_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gacha_draws_user_drawn", "gacha_draws", ["user_id", "drawn_at"])


def downgrade() -> None:
    op.drop_index("ix_gacha_draws_user_drawn", "gacha_draws")
    op.drop_table("gacha_draws")
