"""Gamified intimacy / affection system (task #24).

Each chat interaction adds to affection_score; consecutive daily logins build streak.
When affection_score crosses a threshold, intimacy_level increases.
Levels gate increasingly intimate content in the orchestrator.

Levels:
  0 → 陌生人 (stranger)          — threshold 0
  1 → 普通朋友 (friend)           — threshold 50
  2 → 好朋友 (close friend)       — threshold 150
  3 → 暗戀 (crush)               — threshold 350
  4 → 戀人 (partner)             — threshold 700
  5 → 靈魂伴侶 (soulmate)         — threshold 1200
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import UserRelationship

LEVEL_THRESHOLDS: list[int] = [0, 50, 150, 350, 700, 1_200]
LEVEL_NAMES: list[str] = ["陌生人", "普通朋友", "好朋友", "暗戀", "戀人", "靈魂伴侶"]

CHAT_SCORE_DELTA = 2.0      # per message
STREAK_BONUS = 5.0          # extra per-day if streak continues
GIFT_SCORE_DELTA = 10.0     # when a virtual gift is sent
DECAY_PER_DAY = 1.0         # inactive days bleed score slightly

MAX_LEVEL = len(LEVEL_THRESHOLDS) - 1


class IntimacyStatus(NamedTuple):
    level: int
    level_name: str
    score: float
    streak: int
    next_threshold: int | None


def _level_for_score(score: float) -> int:
    lvl = 0
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if score >= threshold:
            lvl = i
    return min(lvl, MAX_LEVEL)


class IntimacyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_or_create(self, telegram_id: int) -> UserRelationship:
        result = await self._session.execute(
            select(UserRelationship).where(UserRelationship.telegram_id == telegram_id)
        )
        rel = result.scalar_one_or_none()
        if rel is None:
            rel = UserRelationship(telegram_id=telegram_id)
            self._session.add(rel)
            await self._session.flush()
        return rel

    async def record_interaction(
        self,
        telegram_id: int,
        *,
        delta: float = CHAT_SCORE_DELTA,
    ) -> UserRelationship:
        """Record a chat interaction, update streak and score."""
        now = datetime.now(timezone.utc)
        rel = await self._get_or_create(telegram_id)

        # Apply inactivity decay before adding new score.
        if rel.last_interaction is not None:
            days_silent = (now - rel.last_interaction).days
            if days_silent > 0:
                rel.affection_score = max(0.0, rel.affection_score - days_silent * DECAY_PER_DAY)

        # Streak logic: consecutive calendar days.
        if rel.last_interaction is not None:
            delta_days = (now.date() - rel.last_interaction.astimezone(timezone.utc).date()).days
            if delta_days == 0:
                pass  # same day, no streak change
            elif delta_days == 1:
                rel.streak_days += 1
                delta += STREAK_BONUS
            else:
                rel.streak_days = 1  # streak broken

        rel.last_interaction = now
        rel.affection_score = rel.affection_score + delta
        rel.intimacy_level = _level_for_score(rel.affection_score)
        await self._session.flush()
        return rel

    async def record_gift(self, telegram_id: int) -> UserRelationship:
        return await self.record_interaction(telegram_id, delta=GIFT_SCORE_DELTA)

    async def get_status(self, telegram_id: int) -> IntimacyStatus:
        result = await self._session.execute(
            select(UserRelationship).where(UserRelationship.telegram_id == telegram_id)
        )
        rel = result.scalar_one_or_none()
        if rel is None:
            return IntimacyStatus(0, LEVEL_NAMES[0], 0.0, 0, LEVEL_THRESHOLDS[1])

        level = rel.intimacy_level
        next_threshold = LEVEL_THRESHOLDS[level + 1] if level < MAX_LEVEL else None
        return IntimacyStatus(
            level=level,
            level_name=LEVEL_NAMES[level],
            score=rel.affection_score,
            streak=rel.streak_days,
            next_threshold=next_threshold,
        )

    async def intimacy_level(self, telegram_id: int) -> int:
        """Convenience: return just the numeric level."""
        status = await self.get_status(telegram_id)
        return status.level
