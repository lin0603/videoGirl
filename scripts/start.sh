#!/usr/bin/env bash
set -euo pipefail

# Run database migrations (idempotent) before starting services.
uv run --python python3.11 alembic upgrade head

# Start the admin web UI + Telegram bot worker.
exec uv run --python python3.11 python -m admin.main
