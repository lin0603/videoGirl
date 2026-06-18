"""Gamified intimacy / affection system (task #24).

Tracks intimacy level, affection score, and daily streak. Levels unlock
progressively more intimate content and tone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger
from shared.repositories.user_repo import UserRepository

logger = get_logger("shared.intimacy")

# Score thresholds per level. LEVEL_THRESHOLDS[0] is 0; crossing LEVEL_THRESHOLDS[i]
# moves the user to level i. Level 0 means no threshold reached yet.
LEVEL_THRESHOLDS = [0, 100, 300, 600, 1000, 1500, 2200, 3000]
MAX_LEVEL = len(LEVEL_THRESHOLDS) - 1

CHAT_SCORE_DELTA = 5
GIFT_SCORE_DELTA = 25
STREAK_BONUS = 1  # extra point per day of current streak

# Points lost per missed day (capped).
DECAY_PER_MISSED_DAY = 3
MAX_DECAY = 30

_LEVEL_NAMES = {
    0: "初識的曖昧",
    1: "逐漸靠近",
    2: "有點甜了",
    3: "心動戀人",
    4: "親密伴侶",
    5: "靈魂伴侶",
    6: "無可取代",
    7: "命中註定",
}


@dataclass
class IntimacyStatus:
    level: int
    level_name: str
    score: float
    streak: int
    next_threshold: int | None

    @property
    def affection_score(self) -> float:
        return self.score

    @property
    def streak_days(self) -> int:
        return self.streak


@dataclass
class IntimacyProgress:
    level: int
    affection_score: float
    streak_days: int
    next_level_score: float
    progress_pct: float


class IntimacyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    async def record_interaction(
        self, user_id: int, *, delta: float = CHAT_SCORE_DELTA
    ) -> IntimacyStatus:
        """Update streak and affection score when user interacts."""
        user = await self.repo.get_by_telegram_id(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")

        today = self._today()
        last = user.last_interaction_date

        if last is None:
            user.streak_days = 1
        else:
            last_date = last.date()
            if last_date == today:
                pass
            elif last_date == today - timedelta(days=1):
                user.streak_days += 1
            else:
                missed_days = (today - last_date).days - 1
                decay = min(missed_days * DECAY_PER_MISSED_DAY, MAX_DECAY)
                user.affection_score = max(0.0, user.affection_score - decay)
                user.streak_days = 1

        user.affection_score += delta
        user.affection_score += min(user.streak_days * STREAK_BONUS, 10.0)
        user.intimacy_level = self._level_from_score(user.affection_score)
        user.last_interaction_date = datetime.now(timezone.utc)
        await self.session.commit()

        logger.info(
            "intimacy_interaction",
            user_id=user_id,
            level=user.intimacy_level,
            score=user.affection_score,
            streak=user.streak_days,
        )
        return self._status(user)

    async def record_gift(self, user_id: int) -> IntimacyStatus:
        """Award a larger affection boost when the user sends a gift."""
        return await self.record_interaction(user_id, delta=GIFT_SCORE_DELTA)

    async def get_status(self, user_id: int) -> IntimacyStatus:
        user = await self.repo.get_by_telegram_id(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")
        return self._status(user)

    async def get_progress(self, user_id: int) -> IntimacyProgress:
        user = await self.repo.get_by_telegram_id(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")
        return self._progress(user)

    async def intimacy_level(self, user_id: int) -> int:
        status = await self.get_status(user_id)
        return status.level

    @staticmethod
    def _status(user) -> IntimacyStatus:
        level = max(0, min(MAX_LEVEL, user.intimacy_level))
        next_threshold = LEVEL_THRESHOLDS[level + 1] if level < MAX_LEVEL else None
        return IntimacyStatus(
            level=level,
            level_name=_LEVEL_NAMES.get(level, "未知"),
            score=user.affection_score,
            streak=user.streak_days,
            next_threshold=next_threshold,
        )

    @staticmethod
    def _progress(user) -> IntimacyProgress:
        level = max(0, min(MAX_LEVEL, user.intimacy_level))
        current_base = LEVEL_THRESHOLDS[level]
        next_base = LEVEL_THRESHOLDS[level + 1] if level < MAX_LEVEL else current_base
        score_into_level = max(0, user.affection_score - current_base)
        span = max(1, next_base - current_base)
        pct = min(100.0, (score_into_level / span) * 100)
        return IntimacyProgress(
            level=level,
            affection_score=user.affection_score,
            streak_days=user.streak_days,
            next_level_score=next_base,
            progress_pct=round(pct, 1),
        )

    @staticmethod
    def _level_from_score(score: float) -> int:
        level = 0
        for idx, threshold in enumerate(LEVEL_THRESHOLDS[1:], start=1):
            if score >= threshold:
                level = idx
            else:
                break
        return min(level, MAX_LEVEL)

    @staticmethod
    def _today() -> date:
        return datetime.now(timezone.utc).date()


def intimacy_prompt_line(level: int) -> str:
    """Return a system-prompt instruction based on intimacy level."""
    if level >= 5:
        return "你們的親密度很高，可以更直白地表達想念與佔有慾，偶爾說些情話或撒嬌的承諾。"
    if level >= 3:
        return "你們已經有些親密，可以主動關心、說想他、用比較甜的暱稱。"
    return "你們才剛認識不久，保持溫柔、禮貌又有點害羞的距離感，慢慢建立信任。"
