import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from shared.config import settings
from shared.logging import get_logger
from shared.redis import RedisClient

logger = get_logger("bot.rate_limit")

# 每 60 秒最多 20 則訊息。
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_MAX_REQUESTS = 20


class RateLimitMiddleware(BaseMiddleware):
    def __init__(
        self,
        redis_client: RedisClient | None = None,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        max_requests: int = DEFAULT_MAX_REQUESTS,
    ) -> None:
        self.redis_client = redis_client or RedisClient(settings.redis_url)
        self.window_seconds = window_seconds
        self.max_requests = max_requests

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else 0
        if user_id == 0:
            return await handler(event, data)

        key = f"rate_limit:{user_id}"
        now = time.time()
        window_start = now - self.window_seconds

        client = await self.redis_client.connect()
        async with client.pipeline() as pipe:
            await pipe.zremrangebyscore(key, 0, window_start)
            await pipe.zcard(key)
            await pipe.zadd(key, {str(now): now})
            await pipe.expire(key, self.window_seconds)
            results = await pipe.execute()

        current_count = results[1]
        if current_count >= self.max_requests:
            logger.warning(
                "rate_limit_exceeded",
                user_id=user_id,
                current_count=current_count,
            )
            await event.answer(
                "你發送得太快了，請稍後再試。"
            )
            return None

        return await handler(event, data)
