"""add voice settings to users

Revision ID: 0737c1326261
Revises: b5e1a2c3d4f5
Create Date: 2026-06-18 12:36:15.006498

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0737c1326261'
down_revision: Union[str, Sequence[str], None] = 'b5e1a2c3d4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add voice settings columns to users table."""
    op.add_column("users", sa.Column("voice_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("voice_provider", sa.String(length=32), nullable=False, server_default=sa.text("'edge-tts'")))
    op.add_column("users", sa.Column("voice_speed", sa.Float(), nullable=False, server_default=sa.text("1.0")))
    op.add_column("users", sa.Column("voice_reference_audio_url", sa.String(length=1024), nullable=True))
    op.add_column("users", sa.Column("voice_reference_audio_path", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    """Remove voice settings columns from users table."""
    op.drop_column("users", "voice_reference_audio_path")
    op.drop_column("users", "voice_reference_audio_url")
    op.drop_column("users", "voice_speed")
    op.drop_column("users", "voice_provider")
    op.drop_column("users", "voice_enabled")
