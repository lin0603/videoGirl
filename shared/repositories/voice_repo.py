from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Voice


class VoiceRepository:
    """Read access to the admin-managed voice-category catalog."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active(self) -> list[Voice]:
        result = await self.session.execute(
            select(Voice).where(Voice.active.is_(True)).order_by(Voice.slug)
        )
        return list(result.scalars().all())

    async def get(self, slug: str) -> Voice | None:
        result = await self.session.execute(select(Voice).where(Voice.slug == slug))
        return result.scalar_one_or_none()
