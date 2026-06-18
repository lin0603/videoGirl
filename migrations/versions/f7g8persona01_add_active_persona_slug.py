"""add active_persona_slug to users (task #26)

Revision ID: f7g8persona01
Revises: e6f7gifts01
Create Date: 2026-06-19 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "f7g8persona01"
down_revision = "e6f7gifts01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "active_persona_slug",
            sa.String(64),
            nullable=False,
            server_default="xiaorou",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "active_persona_slug")
