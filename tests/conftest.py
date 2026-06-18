import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from shared.config import Settings
from shared.db import _asyncpg_to_asyncpg_url


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set default env vars for the test suite."""
    # These defaults match docker-compose.dev.yml.
    defaults = {
        "telegram_token": "test-token",
        "postgres_url": "postgresql://videogirl:videogirl@localhost:5432/videogirl",
        "redis_url": "redis://localhost:6379/0",
        "ollama_base_url": "http://localhost:11434",
        "comfyui_base_url": "http://localhost:8188",
        "breezyvoice_base_url": "http://localhost:8080",
        "embedding_model": "BAAI/bge-m3",
        "model_name": "test-model",
        "log_level": "INFO",
        "admin_username": "admin",
        "admin_password": "admin",
        "admin_secret_key": "test-secret",
    }
    # Use os.environ.setdefault so existing values (e.g. from CI) are respected.
    import os

    for key, value in defaults.items():
        os.environ.setdefault(key, value)
    from shared.config import get_settings

    get_settings.cache_clear()
    yield


@pytest.fixture
def valid_settings(monkeypatch):
    """Provide a fully configured Settings instance for tests."""
    env = {
        "telegram_token": "test-token",
        "postgres_url": "postgresql://videogirl:videogirl@localhost:5432/videogirl",
        "redis_url": "redis://localhost:6379/0",
        "ollama_base_url": "http://localhost:11434",
        "comfyui_base_url": "http://localhost:8188",
        "breezyvoice_base_url": "http://localhost:8080",
        "embedding_model": "BAAI/bge-m3",
        "model_name": "test-model",
        "log_level": "INFO",
        "admin_username": "admin",
        "admin_password": "admin",
        "admin_secret_key": "test-secret",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


@pytest.fixture(scope="session")
def db_engine():
    from shared.config import settings

    engine = create_async_engine(_asyncpg_to_asyncpg_url(settings.postgres_url), future=True)
    yield engine
    engine.sync_engine.dispose()
