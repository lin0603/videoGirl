"""memory system tables (conversation_turns, memories, user_profile, user_relationships)

Revision ID: b5e1a2c3d4f5
Revises: 03d3c7de3fc7
Create Date: 2026-06-18 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5e1a2c3d4f5"
down_revision: Union[str, Sequence[str], None] = "03d3c7de3fc7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBED_DIM = 1024  # BAAI/bge-m3


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversation_turns (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL CHECK (role IN ('system','user','assistant')),
            content TEXT NOT NULL,
            tokens_estimate INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_turns_user_time ON conversation_turns (telegram_id, created_at DESC);"
    )

    op.execute(
        f"""
        CREATE TABLE memories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            memory_type VARCHAR(32) NOT NULL DEFAULT 'fact',
            importance REAL NOT NULL DEFAULT 0.5,
            embedding vector({EMBED_DIM}),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_accessed TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX ix_memories_user ON memories (telegram_id);")
    op.execute(
        "CREATE INDEX ix_memories_embedding ON memories "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
    )

    op.execute(
        """
        CREATE TABLE user_profile (
            telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
            traits JSONB NOT NULL DEFAULT '[]'::jsonb,
            preferences JSONB NOT NULL DEFAULT '[]'::jsonb,
            life_facts JSONB NOT NULL DEFAULT '[]'::jsonb,
            summary TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE user_relationships (
            telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
            intimacy_level INTEGER NOT NULL DEFAULT 0,
            affection_score REAL NOT NULL DEFAULT 0,
            streak_days INTEGER NOT NULL DEFAULT 0,
            last_interaction TIMESTAMPTZ,
            special_dates JSONB NOT NULL DEFAULT '[]'::jsonb
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_relationships;")
    op.execute("DROP TABLE IF EXISTS user_profile;")
    op.execute("DROP TABLE IF EXISTS memories;")
    op.execute("DROP TABLE IF EXISTS conversation_turns;")
