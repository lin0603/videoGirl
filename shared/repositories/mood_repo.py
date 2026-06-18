"""Async CRUD for companion mood state."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import CompanionMood


class MoodRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int, persona_slug: str) -> CompanionMood | None:
        result = await self.session.execute(
            select(CompanionMood).where(
                CompanionMood.user_id == user_id,
                CompanionMood.persona_slug == persona_slug,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self, user_id: int, persona_slug: str
    ) -> CompanionMood:
        mood = await self.get(user_id, persona_slug)
        if mood is None:
            now = datetime.now(timezone.utc)
            mood = CompanionMood(
                user_id=user_id,
                persona_slug=persona_slug,
                affection=0.0,
                longing=0.0,
                playfulness=0.0,
                upset=0.0,
                last_interaction_at=now,
                created_at=now,
                updated_at=now,
            )
            self.session.add(mood)
            await self.session.commit()
            await self.session.refresh(mood)
        return mood

    async def save(self, mood: CompanionMood) -> CompanionMood:
        mood.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(mood)
        return mood
