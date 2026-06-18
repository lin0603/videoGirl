FROM python:3.11-slim

WORKDIR /app
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=never

# Install uv, curl for healthchecks, and ffmpeg for voice conversion.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Copy dependency definitions first for layer caching.
COPY pyproject.toml /app/pyproject.toml

# Install production dependencies only.
RUN uv sync --no-dev --python python3.11

# Copy application code.
COPY . /app

# Expose the admin web UI port.
EXPOSE 8000

# Default healthcheck used by Coolify; can be overridden.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD uv run --python python3.11 python -m shared.health || exit 1

# Start migrations then the admin UI + bot worker.
CMD ["bash", "scripts/start.sh"]
