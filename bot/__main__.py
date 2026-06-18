import asyncio
import sys

from bot.dispatcher import start_bot
from shared.logging import configure_logging, get_logger


def main() -> None:
    configure_logging()
    logger = get_logger("bot.main")
    logger.info("bot_scaffold_ready")
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("bot_stopped_by_user")
        sys.exit(0)


if __name__ == "__main__":
    main()
