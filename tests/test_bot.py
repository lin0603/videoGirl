import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from unittest.mock import AsyncMock

from bot.dispatcher import create_dispatcher
from shared.config import settings
from shared.db import _asyncpg_to_asyncpg_url
from shared.repositories.user_repo import UserRepository


class MockedBot(Bot):
    def __init__(self, token: str = "123456:TEST") -> None:
        super().__init__(token=token)
        self.session = AsyncMock()
        self.session.make_request = AsyncMock(return_value={})


def make_user(telegram_id: int = 42, username: str = "testuser", full_name: str = "Test User") -> User:
    return User(
        id=telegram_id,
        is_bot=False,
        first_name=full_name.split()[0],
        last_name=" ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else "",
        username=username,
        language_code="zh-TW",
    )


def make_chat(chat_id: int = 42) -> Chat:
    return Chat(id=chat_id, type="private")


def make_message(text: str, user: User | None = None, chat_id: int = 42) -> Message:
    return Message(
        message_id=1,
        date=0,
        chat=make_chat(chat_id),
        from_user=user or make_user(),
        text=text,
    )


def make_callback(data: str, user: User | None = None, chat_id: int = 42) -> CallbackQuery:
    return CallbackQuery(
        id="1",
        from_user=user or make_user(),
        chat_instance="1",
        data=data,
        message=make_message("prompt", user or make_user(), chat_id),
    )


@pytest.fixture(scope="session")
def event_loop():
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def db_engine():
    engine = create_async_engine(_asyncpg_to_asyncpg_url(settings.postgres_url), future=True)
    yield engine
    engine.sync_engine.dispose()


@pytest.fixture(autouse=True)
async def clean_users(db_engine):
    async with db_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))


@pytest.fixture
def bot() -> MockedBot:
    return MockedBot()


@pytest.fixture
def dp() -> Dispatcher:
    return create_dispatcher()


async def get_user(session: AsyncSession, telegram_id: int):
    repo = UserRepository(session)
    return await repo.get_by_telegram_id(telegram_id)


@pytest.mark.asyncio
async def test_start_onboarding_flow(dp: Dispatcher, bot: MockedBot, db_engine) -> None:
    user = make_user(telegram_id=1001)

    await dp.feed_update(bot, Update(update_id=1, message=make_message("/start", user)))

    async with AsyncSession(bind=db_engine) as session:
        db_user = await get_user(session, 1001)
        assert db_user is not None
        assert db_user.age_verified_at is None
        assert db_user.nsfw_opt_in is False

    await dp.feed_update(
        bot,
        Update(update_id=2, message=make_message("1995", user)),
    )

    async with AsyncSession(bind=db_engine) as session:
        db_user = await get_user(session, 1001)
        assert db_user.age_verified_at is not None
        assert db_user.nsfw_opt_in is False

    await dp.feed_update(
        bot,
        Update(update_id=3, callback_query=make_callback("nsfw_yes", user)),
    )

    async with AsyncSession(bind=db_engine) as session:
        db_user = await get_user(session, 1001)
        assert db_user.nsfw_opt_in is True


@pytest.mark.asyncio
async def test_age_gate_rejects_underage(dp: Dispatcher, bot: MockedBot, db_engine) -> None:
    user = make_user(telegram_id=1002)

    await dp.feed_update(bot, Update(update_id=1, message=make_message("/start", user)))
    current_year = 2026
    birth_year = current_year - 10
    await dp.feed_update(
        bot,
        Update(update_id=2, message=make_message(str(birth_year), user)),
    )

    async with AsyncSession(bind=db_engine) as session:
        db_user = await get_user(session, 1002)
        assert db_user.age_verified_at is None


@pytest.mark.asyncio
async def test_toggle_nsfw_flips_flag(dp: Dispatcher, bot: MockedBot, db_engine) -> None:
    user = make_user(telegram_id=1003)

    async with AsyncSession(bind=db_engine) as session:
        repo = UserRepository(session)
        await repo.create_or_update(
            telegram_id=1003,
            username=user.username,
            display_name=user.full_name,
        )
        await repo.set_age_verified(1003)

    await dp.feed_update(bot, Update(update_id=1, message=make_message("/toggle_nsfw", user)))

    async with AsyncSession(bind=db_engine) as session:
        db_user = await get_user(session, 1003)
        assert db_user.nsfw_opt_in is True

    await dp.feed_update(bot, Update(update_id=2, message=make_message("/toggle_nsfw", user)))

    async with AsyncSession(bind=db_engine) as session:
        db_user = await get_user(session, 1003)
        assert db_user.nsfw_opt_in is False


@pytest.mark.asyncio
async def test_help_command(dp: Dispatcher, bot: MockedBot) -> None:
    user = make_user()
    await dp.feed_update(bot, Update(update_id=1, message=make_message("/help", user)))
    bot.session.assert_called()
