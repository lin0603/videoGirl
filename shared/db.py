import asyncpg
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.config import settings


def _asyncpg_to_asyncpg_url(dsn: str) -> str:
    """Convert a postgresql:// DSN to postgresql+asyncpg:// for SQLAlchemy."""
    if dsn.startswith("postgresql://") and not dsn.startswith("postgresql+asyncpg://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


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


_engine = create_async_engine(_asyncpg_to_asyncpg_url(settings.postgres_url), future=True)
AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
