import pytest

from shared.db import Database
from shared.health import check_postgres, check_redis
from shared.redis import RedisClient


@pytest.mark.asyncio
async def test_postgres_has_pgvector():
    db = Database()
    await db.connect()
    try:
        ok, message = await check_postgres()
        assert ok, message
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_redis_pings():
    client = RedisClient()
    try:
        ok, message = await check_redis()
        assert ok, message
    finally:
        await client.disconnect()
