"""Special dates service: birthdays, anniversaries, proactive gift messages (task #33)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger
from shared.models import SpecialDate

logger = get_logger("shared.special_dates")


class SpecialDateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        *,
        user_id: int,
        date_type: str,
        month: int,
        day: int,
        label: str,
        recurrent: bool = True,
    ) -> SpecialDate:
        """Create or replace a special date (one per user+type combination)."""
        result = await self.session.execute(
            select(SpecialDate).where(
                SpecialDate.user_id == user_id,
                SpecialDate.date_type == date_type,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = SpecialDate(user_id=user_id, date_type=date_type)
            self.session.add(row)

        row.month = month
        row.day = day
        row.label = label
        row.recurrent = recurrent
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_for_user(self, user_id: int) -> Sequence[SpecialDate]:
        result = await self.session.execute(
            select(SpecialDate).where(SpecialDate.user_id == user_id)
        )
        return result.scalars().all()

    async def get_due_today(self) -> Sequence[SpecialDate]:
        """Return all special dates whose month/day matches today (UTC) and haven't been greeted yet today."""
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(SpecialDate).where(
                SpecialDate.month == now.month,
                SpecialDate.day == now.day,
            )
        )
        rows = result.scalars().all()

        due = []
        for row in rows:
            if row.last_greeted_at is None:
                due.append(row)
                continue
            # Skip if already greeted today.
            already = (
                row.last_greeted_at.year == now.year
                and row.last_greeted_at.month == now.month
                and row.last_greeted_at.day == now.day
            )
            if not already:
                due.append(row)
        return due

    async def mark_greeted(self, special_date: SpecialDate) -> None:
        special_date.last_greeted_at = datetime.now(timezone.utc)
        if not special_date.recurrent:
            await self.session.delete(special_date)
        await self.session.commit()
