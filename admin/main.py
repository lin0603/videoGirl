"""Entrypoint that runs the FastAPI admin UI and the Telegram bot together."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from admin.app import app as admin_app
from bot.dispatcher import start_bot
from shared.config import get_settings
from shared.logging import get_logger

logger = get_logger("admin.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    shutdown_event = asyncio.Event()
    logger.info("admin_starting", host=settings.admin_host, port=settings.admin_port)
    bot_task = asyncio.create_task(start_bot(shutdown_event))
    yield
    logger.info("admin_shutting_down")
    shutdown_event.set()
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
