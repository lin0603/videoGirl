import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from shared.config import settings
from shared.logging import configure_logging, get_logger

from bot.handlers import chat, commands, onboarding, payments
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
    # Stars payments: the pre_checkout handler needs a DB session too, or
    # answerPreCheckoutQuery never runs and every payment is cancelled.
    dp.pre_checkout_query.middleware(DbSessionMiddleware())

    dp.include_router(commands.get_router())
    dp.include_router(onboarding.get_router())
    dp.include_router(payments.get_router())
    dp.include_router(chat.get_router())

    return dp


def create_bot() -> Bot:
    return Bot(
        token=settings.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def start_bot(
    shutdown_event: asyncio.Event | None = None,
    bot: Bot | None = None,
    dp: Dispatcher | None = None,
) -> None:
    bot = bot or create_bot()
    dp = dp or create_dispatcher()
    logger.info("bot_starting")
    await db.connect()
    try:
        if shutdown_event is None:
            await dp.start_polling(bot)
        else:
            polling_task = asyncio.create_task(dp.start_polling(bot))
            await shutdown_event.wait()
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
    finally:
        await db.disconnect()
        await bot.session.close()
