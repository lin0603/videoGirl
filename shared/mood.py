"""Companion mood model and service (task #32).

Mood is stored per (user, persona) as four dimensions in the range [-1, 1]:
- affection: how close/loving she feels
- longing: how much she misses the user
- playfulness: teasing/energetic mood
- upset: sad/annoyed/neglected

The model decays toward baseline over time and is bumped by events such as
chat, gifts, or silence. A short mood phrase is injected into the system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger
from shared.repositories.mood_repo import MoodRepository

logger = get_logger("shared.mood")

# Time constants
_SILENCE_THRESHOLD_SECONDS = 4 * 3600  # 4 hours
_DECAY_HALF_LIFE_HOURS = 12.0

# Deltas per event type (clamped to [-1, 1])
EVENT_DELTAS: dict[str, dict[str, float]] = {
    "chat": {"affection": 0.06, "longing": -0.08, "playfulness": 0.04, "upset": -0.05},
    "warm_chat": {"affection": 0.10, "longing": -0.10, "playfulness": 0.06, "upset": -0.08},
    "gift": {"affection": 0.25, "longing": -0.10, "playfulness": 0.10, "upset": -0.20},
    "silence": {"affection": -0.02, "longing": 0.12, "playfulness": -0.04, "upset": 0.05},
    "ignored": {"affection": -0.05, "longing": 0.05, "playfulness": -0.06, "upset": 0.10},
}


@dataclass
class MoodSnapshot:
    affection: float
    longing: float
    playfulness: float
    upset: float
    dominant: str
    phrase: str


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _apply_decay(value: float, elapsed_hours: float) -> float:
    """Exponential decay toward zero."""
    if value == 0.0:
        return 0.0
    decay = 0.5 ** (elapsed_hours / _DECAY_HALF_LIFE_HOURS)
    return value * decay


def _dominant_mood(affection: float, longing: float, playfulness: float, upset: float) -> str:
    scores = {
        "affection": affection,
        "longing": longing,
        "playfulness": playfulness,
        "upset": upset,
    }
    # Require a meaningful amplitude to declare a dominant mood.
    dominant, score = max(scores.items(), key=lambda item: abs(item[1]))
    if abs(score) < 0.15:
        return "neutral"
    return dominant


def _mood_phrase(dominant: str, *, upset: float, longing: float, affection: float) -> str:
    """Return a short phrase describing current mood for the system prompt."""
    phrases = {
        "affection": "心裡暖暖的、很喜歡你",
        "playfulness": "心情輕快、想鬧你",
        "longing": "好想你、等有點寂寞",
        "upset": "有點小委屈、需要哄",
        "neutral": "平靜地陪著你",
    }
    phrase = phrases.get(dominant, phrases["neutral"])

    # Blend secondary emotion for richer prompts.
    if dominant == "longing" and upset > 0.25:
        phrase = "等你等得有點難過，想被關心"
    elif dominant == "affection" and longing > 0.2:
        phrase = "很喜歡你，也有點想你"
    elif dominant == "upset" and affection > 0.2:
        phrase = "雖然有點小情緒，但還是喜歡你"

    return phrase


def _build_snapshot(affection: float, longing: float, playfulness: float, upset: float) -> MoodSnapshot:
    dominant = _dominant_mood(affection, longing, playfulness, upset)
    return MoodSnapshot(
        affection=affection,
        longing=longing,
        playfulness=playfulness,
        upset=upset,
        dominant=dominant,
        phrase=_mood_phrase(
            dominant,
            upset=upset,
            longing=longing,
            affection=affection,
        ),
    )


class MoodService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = MoodRepository(session)

    async def get_mood(self, user_id: int, persona_slug: str) -> MoodSnapshot:
        mood = await self.repo.get_or_create(user_id, persona_slug)
        return self._apply_passive_decay(mood)

    async def process_event(
        self,
        user_id: int,
        persona_slug: str,
        event_type: Literal["chat", "warm_chat", "gift", "silence", "ignored"],
    ) -> MoodSnapshot:
        """Update mood for an interaction event and return the current snapshot."""
        mood = await self.repo.get_or_create(user_id, persona_slug)
        snapshot = self._apply_passive_decay(mood)
        deltas = EVENT_DELTAS.get(event_type, EVENT_DELTAS["chat"])

        mood.affection = _clamp(snapshot.affection + deltas["affection"])
        mood.longing = _clamp(snapshot.longing + deltas["longing"])
        mood.playfulness = _clamp(snapshot.playfulness + deltas["playfulness"])
        mood.upset = _clamp(snapshot.upset + deltas["upset"])
        mood.last_interaction_at = datetime.now(timezone.utc)

        await self.repo.save(mood)
        logger.debug(
            "mood_event_applied",
            user_id=user_id,
            persona_slug=persona_slug,
            event_type=event_type,
            affection=mood.affection,
            longing=mood.longing,
            playfulness=mood.playfulness,
            upset=mood.upset,
        )
        return _build_snapshot(mood.affection, mood.longing, mood.playfulness, mood.upset)

    async def process_chat_message(
        self,
        user_id: int,
        persona_slug: str,
        text: str = "",
    ) -> str:
        """Convenience: apply chat/warm_chat or silence decay and return a prompt phrase."""
        mood = await self.repo.get_or_create(user_id, persona_slug)
        elapsed = datetime.now(timezone.utc) - mood.last_interaction_at
        if elapsed > timedelta(seconds=_SILENCE_THRESHOLD_SECONDS):
            event_type = "silence"
        elif self._is_warm(text):
            event_type = "warm_chat"
        else:
            event_type = "chat"
        snapshot = await self.process_event(user_id, persona_slug, event_type)
        return snapshot.phrase

    @staticmethod
    def _is_warm(text: str) -> bool:
        """Very cheap heuristic for affectionate messages."""
        warm_keywords = {
            "想妳",
            "愛妳",
            "喜歡妳",
            "寶貝",
            "親愛的",
            "抱抱",
            "晚安",
            "早安",
            "辛苦",
            "謝謝",
        }
        lowered = text.lower()
        return any(k in lowered for k in warm_keywords)

    def _apply_passive_decay(self, mood) -> MoodSnapshot:
        """Decay stored mood dimensions toward zero based on elapsed time."""
        now = datetime.now(timezone.utc)
        elapsed = now - mood.last_interaction_at
        elapsed_hours = elapsed.total_seconds() / 3600.0

        return _build_snapshot(
            affection=_apply_decay(mood.affection, elapsed_hours),
            longing=_apply_decay(mood.longing, elapsed_hours),
            playfulness=_apply_decay(mood.playfulness, elapsed_hours),
            upset=_apply_decay(mood.upset, elapsed_hours),
        )


def format_mood_for_prompt(phrase: str) -> str:
    """Format the mood phrase for injection into the system prompt."""
    return f"此刻心情：{phrase}。請讓這份心情自然影響你的語氣，但不要直接複述這句話。"
