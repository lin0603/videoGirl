#!/usr/bin/env bash
set -euo pipefail

# Run database migrations (idempotent) before starting the bot.
uv run --python python3.11 alembic upgrade head

# Start the Telegram bot.
exec uv run --python python3.11 python -m bot
