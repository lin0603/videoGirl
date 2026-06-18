"""voices catalog + user voice_slug; BreezyVoice-only defaults

Revision ID: c7a1voicecat01
Revises: 0737c1326261
Create Date: 2026-06-18 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7a1voicecat01"
down_revision: Union[str, Sequence[str], None] = "0737c1326261"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REF = "/home/bygpu/mentorai-breezyvoice/inputs"


def upgrade() -> None:
    # voices catalog (admin-managed voice categories)
    op.create_table(
        "voices",
        sa.Column("slug", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False,
                  server_default=sa.text("'breezevoice'")),
        sa.Column("reference_audio_path", sa.String(length=1024), nullable=True),
        sa.Column("reference_transcript", sa.String(length=2048), nullable=True),
        sa.Column("tempo", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    # seed categories. 'default' = the server's built-in reference voice;
    # 'short' = the 8s reference clip (needs its matching transcript).
    ref8_text = "有什麼有趣的滑鼠的手機或電腦可以玩他們就拓展自己的想象力找一些樂子"
    op.execute(
        sa.text(
            "INSERT INTO voices "
            "(slug, name, provider, reference_audio_path, reference_transcript, tempo, active) VALUES "
            "('default', '預設女聲', 'breezevoice', NULL, NULL, 1.0, true), "
            "('short', '俏皮短音', 'breezevoice', :path, :tt, 1.05, true)"
        ).bindparams(path=f"{REF}/prompt-ref-8s.wav", tt=ref8_text)
    )

    # user's chosen category + BreezyVoice-only defaults
    op.add_column("users", sa.Column("voice_slug", sa.String(length=64),
                  nullable=False, server_default=sa.text("'default'")))
    op.alter_column("users", "voice_provider", server_default=sa.text("'breezevoice'"))
    op.execute("UPDATE users SET voice_provider = 'breezevoice' WHERE voice_provider = 'edge-tts'")


def downgrade() -> None:
    op.alter_column("users", "voice_provider", server_default=sa.text("'edge-tts'"))
    op.drop_column("users", "voice_slug")
    op.drop_table("voices")
