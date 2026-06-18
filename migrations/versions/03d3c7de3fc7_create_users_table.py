"""create users table

Revision ID: 03d3c7de3fc7
Revises: 12028d6d28fa
Create Date: 2026-06-18 12:08:04.057795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '03d3c7de3fc7'
down_revision: Union[str, Sequence[str], None] = '12028d6d28fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the users table."""
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("age_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nsfw_opt_in", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default=sa.text("'zh-TW'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("telegram_id"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=False)


def downgrade() -> None:
    """Drop the users table."""
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
