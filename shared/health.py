import asyncio
import json
import sys

import asyncpg
import redis.asyncio as redis

from shared.config import settings
from shared.logging import configure_logging, get_logger


async def check_postgres() -> tuple[bool, str]:
    try:
        conn = await asyncpg.connect(settings.postgres_url)
        try:
            row = await conn.fetchrow(
                "SELECT extname FROM pg_extension WHERE extname = 'vector'"
            )
            if row is None:
                return False, "pgvector extension not enabled"
            return True, "ok"
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"postgres connection failed: {exc}"


async def check_redis() -> tuple[bool, str]:
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.ping()
            return True, "ok"
        finally:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001
        return False, f"redis connection failed: {exc}"


async def main() -> int:
    configure_logging()
    logger = get_logger("shared.health")

    pg_ok, pg_msg = await check_postgres()
    redis_ok, redis_msg = await check_redis()

    status = "ok" if pg_ok and redis_ok else "error"
    result = {
        "status": status,
        "postgres": {"ok": pg_ok, "message": pg_msg},
        "redis": {"ok": redis_ok, "message": redis_msg},
    }

    print(json.dumps(result, ensure_ascii=False))
    logger.info("health_check", **result)

    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
