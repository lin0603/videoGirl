from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from shared.config import settings
from shared.logging import configure_logging, get_logger

from bot.handlers import chat, commands, onboarding
from bot.middlewares.db_session import DbSessionMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from shared.db import db


configure_logging()
logger = get_logger("bot.dispatcher")


def create_dispatcher() -> Dispatcher:
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.message.middleware(DbSessionMiddleware())
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())

    dp.include_router(commands.get_router())
    dp.include_router(onboarding.get_router())
    dp.include_router(chat.get_router())

    return dp


def create_bot() -> Bot:
    return Bot(
        token=settings.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def start_bot() -> None:
    bot = create_bot()
    dp = create_dispatcher()
    logger.info("bot_starting")
    await db.connect()
    try:
        await dp.start_polling(bot)
    finally:
        await db.disconnect()
        await bot.session.close()
