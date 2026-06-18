"""Entrypoint that runs the FastAPI admin UI and the Telegram bot together."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from admin.app import app as admin_app
from bot.dispatcher import create_bot, create_dispatcher, start_bot
from shared.config import get_settings
from shared.logging import get_logger
from shared.proactive import ProactiveEngine

logger = get_logger("admin.main")


def _exit_if_bot_dies(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is None:
        logger.error("bot_task_stopped_unexpectedly")
    else:
        logger.exception("bot_task_failed", error=str(exc))
    os._exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    shutdown_event = asyncio.Event()
    logger.info("admin_starting", host=settings.admin_host, port=settings.admin_port)

    bot = create_bot()
    dp = create_dispatcher()
    bot_task = asyncio.create_task(start_bot(shutdown_event, bot=bot, dp=dp))
    bot_task.add_done_callback(_exit_if_bot_dies)

    proactive = ProactiveEngine(bot)
    proactive.start()

    yield

    logger.info("admin_shutting_down")
    proactive.stop()
    shutdown_event.set()
    bot_task.remove_done_callback(_exit_if_bot_dies)
    await bot_task


admin_app.router.lifespan_context = lifespan


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "admin.main:admin_app",
        host=settings.admin_host,
        port=settings.admin_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
