"""add yiting BreezyVoice profile as default

Revision ID: 8d0c1b2a3f4e
Revises: 3fac9c518082
Create Date: 2026-06-18 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8d0c1b2a3f4e"
down_revision: Union[str, Sequence[str], None] = "3fac9c518082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

YITING_PROMPT_AUDIO = "/home/bygpu/mentorai-breezyvoice/inputs/yiting/prompt-seg-0111-24k.wav"
YITING_PROMPT_TEXT = "這個新手教學會不會讓我們對自己有錯誤的認知啊誤以為這麼好玩這麼容易玩"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO voices (
                slug,
                name,
                provider,
                reference_audio_path,
                reference_transcript,
                tempo,
                active,
                sort_order
            )
            VALUES (
                'yiting',
                '依渟',
                'breezevoice',
                :audio_path,
                :prompt_text,
                1.0,
                true,
                -100
            )
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                provider = EXCLUDED.provider,
                reference_audio_path = EXCLUDED.reference_audio_path,
                reference_transcript = EXCLUDED.reference_transcript,
                tempo = EXCLUDED.tempo,
                active = EXCLUDED.active,
                sort_order = EXCLUDED.sort_order
            """
        ).bindparams(audio_path=YITING_PROMPT_AUDIO, prompt_text=YITING_PROMPT_TEXT)
    )
    op.alter_column("users", "voice_slug", server_default=sa.text("'yiting'"))
    op.execute("UPDATE users SET voice_slug = 'yiting' WHERE voice_slug = 'default'")


def downgrade() -> None:
    op.execute("UPDATE users SET voice_slug = 'default' WHERE voice_slug = 'yiting'")
    op.alter_column("users", "voice_slug", server_default=sa.text("'default'"))
    op.execute("DELETE FROM voices WHERE slug = 'yiting'")
