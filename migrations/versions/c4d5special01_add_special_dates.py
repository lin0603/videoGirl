"""add special_dates table

Revision ID: c4d5special01
Revises: b2c3merge01
Create Date: 2026-06-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5special01"
down_revision: Union[str, Sequence[str]] = "b2c3merge01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "special_dates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("date_type", sa.String(32), nullable=False, server_default="birthday"),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("day", sa.Integer, nullable=False),
        sa.Column("recurrent", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_greeted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_special_dates_user_id", "special_dates", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_special_dates_user_id", "special_dates")
    op.drop_table("special_dates")
