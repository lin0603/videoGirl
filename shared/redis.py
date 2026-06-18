import redis.asyncio as redis

from shared.config import settings


class RedisClient:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or settings.redis_url
        self.client: redis.Redis | None = None

    async def connect(self) -> redis.Redis:
        if self.client is None:
            self.client = redis.from_url(self.url, decode_responses=True)
        return self.client

    async def disconnect(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def ping(self) -> bool:
        if self.client is None:
            await self.connect()
        assert self.client is not None
        return await self.client.ping()


redis_client = RedisClient()


async def get_redis() -> redis.Redis:
    if redis_client.client is None:
        await redis_client.connect()
    assert redis_client.client is not None
    return redis_client.client
