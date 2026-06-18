"""add LoRA and image_workflow fields to personas

Revision ID: d5e6lora01
Revises: c4d5special01
Create Date: 2026-06-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6lora01"
down_revision: Union[str, Sequence[str]] = "c4d5special01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("personas", sa.Column("lora_name", sa.String(256), server_default="", nullable=False))
    op.add_column("personas", sa.Column("lora_strength", sa.Float, server_default="0.8", nullable=False))
    op.add_column("personas", sa.Column("image_workflow", sa.String(256), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("personas", "image_workflow")
    op.drop_column("personas", "lora_strength")
    op.drop_column("personas", "lora_name")
