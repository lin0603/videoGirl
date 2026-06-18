import asyncpg

from shared.config import settings


class Database:
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or settings.postgres_url
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> asyncpg.Pool:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10)
        return self.pool

    async def disconnect(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def fetchrow(self, query: str, *args):
        if self.pool is None:
            raise RuntimeError("Database not connected")
        return await self.pool.fetchrow(query, *args)

    async def fetch(self, query: str, *args):
        if self.pool is None:
            raise RuntimeError("Database not connected")
        return await self.pool.fetch(query, *args)

    async def execute(self, query: str, *args):
        if self.pool is None:
            raise RuntimeError("Database not connected")
        return await self.pool.execute(query, *args)


db = Database()


async def get_pool() -> asyncpg.Pool:
    if db.pool is None:
        await db.connect()
    assert db.pool is not None
    return db.pool
