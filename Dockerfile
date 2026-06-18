FROM python:3.11-slim

WORKDIR /app

# Install uv and curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Copy dependency definitions first for layer caching.
COPY pyproject.toml /app/pyproject.toml

# Install production dependencies only.
RUN uv sync --no-dev --python python3.11

# Copy application code.
COPY . /app

# Default healthcheck used by Coolify; can be overridden.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD uv run --python python3.11 python -m shared.health || exit 1

# Default command placeholder: run the bot scaffold.
CMD ["uv", "run", "--python", "python3.11", "python", "-m", "bot"]
