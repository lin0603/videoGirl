"""Per-user last-photo cache in Redis for I2V source image (task #15).

When the photo callback delivers an image to Telegram, we also cache the raw
bytes here so subsequent video requests can use it as a source frame.

TTL is 48 h — plenty for a same-session video request; auto-expires after.
"""
from __future__ import annotations

_PHOTO_KEY_FMT = "media:lastphoto:{user_id}"
_PHOTO_TTL = 172_800  # 48 hours


def _key(user_id: int) -> str:
    return _PHOTO_KEY_FMT.format(user_id=user_id)


async def _binary_redis():
    """Binary (no decode) Redis client for storing raw bytes."""
    import redis.asyncio as aioredis
    from shared.config import get_settings
    return aioredis.from_url(get_settings().redis_url, decode_responses=False)


_binary_client = None


async def _get_binary_redis():
    global _binary_client
    if _binary_client is None:
        _binary_client = await _binary_redis()
    return _binary_client


async def store_last_photo(user_id: int, data: bytes) -> None:
    """Cache the most recent generated photo bytes for a user."""
    r = await _get_binary_redis()
    await r.set(_key(user_id), data, ex=_PHOTO_TTL)


async def get_last_photo_bytes(user_id: int) -> bytes | None:
    """Retrieve the most recent cached photo bytes, or None."""
    r = await _get_binary_redis()
    return await r.get(_key(user_id))


async def clear_last_photo(user_id: int) -> None:
    r = await _get_binary_redis()
    await r.delete(_key(user_id))
