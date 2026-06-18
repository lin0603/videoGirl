from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        telegram_id: int,
        username: str | None,
        display_name: str | None,
        locale: str = "zh-TW",
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                display_name=display_name,
                locale=locale,
            )
            self.session.add(user)
        else:
            user.username = username
            user.display_name = display_name
        await self.session.commit()
        return user

    async def set_age_verified(self, telegram_id: int) -> User | None:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        user.age_verified_at = datetime.utcnow()
        await self.session.commit()
        return user

    async def toggle_nsfw(self, telegram_id: int) -> User | None:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        user.nsfw_opt_in = not user.nsfw_opt_in
        await self.session.commit()
        return user

    async def set_nsfw(self, telegram_id: int, opt_in: bool) -> User | None:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        user.nsfw_opt_in = opt_in
        await self.session.commit()
        return user

    async def set_voice_enabled(self, telegram_id: int, enabled: bool) -> User | None:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        user.voice_enabled = enabled
        await self.session.commit()
        return user

    async def set_voice_settings(
        self,
        telegram_id: int,
        *,
        provider: str | None = None,
        speed: float | None = None,
        reference_audio_url: str | None = None,
        reference_audio_path: str | None = None,
    ) -> User | None:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        if provider is not None:
            user.voice_provider = provider
        if speed is not None:
            user.voice_speed = max(0.5, min(2.0, speed))
        if reference_audio_url is not None:
            user.voice_reference_audio_url = reference_audio_url
        if reference_audio_path is not None:
            user.voice_reference_audio_path = reference_audio_path
        await self.session.commit()
        return user
