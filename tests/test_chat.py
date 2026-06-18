import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from unittest.mock import AsyncMock, patch

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
        await conn.execute(text("TRUNCATE TABLE users, conversation_turns, user_profile, memories RESTART IDENTITY CASCADE"))


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
async def test_chat_handler_replies_text(dp: Dispatcher, bot: MockedBot, db_engine) -> None:
    user = make_user(telegram_id=2001)
    async with AsyncSession(bind=db_engine) as session:
        repo = UserRepository(session)
        await repo.create_or_update(
            telegram_id=2001,
            username=user.username,
            display_name=user.full_name,
        )
        await repo.set_age_verified(2001)

    with patch("bot.handlers.chat.respond", new=AsyncMock(return_value="我好想你喔～")) as mock_respond:
        await dp.feed_update(bot, Update(update_id=1, message=make_message("你好", user)))
        mock_respond.assert_awaited_once()

    bot.session.assert_called()


@pytest.mark.asyncio
async def test_chat_handler_sends_voice_when_enabled(dp: Dispatcher, bot: MockedBot, db_engine) -> None:
    user = make_user(telegram_id=2002)
    async with AsyncSession(bind=db_engine) as session:
        repo = UserRepository(session)
        await repo.create_or_update(
            telegram_id=2002,
            username=user.username,
            display_name=user.full_name,
        )
        await repo.set_age_verified(2002)
        await repo.set_voice_enabled(2002, True)

    fake_voice = b"fake ogg bytes"
    with (
        patch("bot.handlers.chat.respond", new=AsyncMock(return_value="我好想你喔～")),
        patch("bot.handlers.chat.synthesize", new=AsyncMock(return_value=fake_voice)) as mock_synth,
    ):
        await dp.feed_update(bot, Update(update_id=1, message=make_message("你好", user)))
        mock_synth.assert_awaited_once()

    bot.session.assert_called()


@pytest.mark.asyncio
async def test_voice_commands_toggle(dp: Dispatcher, bot: MockedBot, db_engine) -> None:
    user = make_user(telegram_id=2003)
    async with AsyncSession(bind=db_engine) as session:
        repo = UserRepository(session)
        await repo.create_or_update(
            telegram_id=2003,
            username=user.username,
            display_name=user.full_name,
        )
        await repo.set_age_verified(2003)

    await dp.feed_update(bot, Update(update_id=1, message=make_message("/voice_on", user)))

    async with AsyncSession(bind=db_engine) as session:
        db_user = await get_user(session, 2003)
        assert db_user.voice_enabled is True

    await dp.feed_update(bot, Update(update_id=2, message=make_message("/voice_off", user)))

    async with AsyncSession(bind=db_engine) as session:
        db_user = await get_user(session, 2003)
        assert db_user.voice_enabled is False


@pytest.mark.asyncio
async def test_chat_handler_rejects_unverified(dp: Dispatcher, bot: MockedBot, db_engine) -> None:
    user = make_user(telegram_id=2004)
    async with AsyncSession(bind=db_engine) as session:
        repo = UserRepository(session)
        await repo.create_or_update(
            telegram_id=2004,
            username=user.username,
            display_name=user.full_name,
        )

    with patch("bot.handlers.chat.respond") as mock_respond:
        await dp.feed_update(bot, Update(update_id=1, message=make_message("你好", user)))
        mock_respond.assert_not_called()

    bot.session.assert_called()
