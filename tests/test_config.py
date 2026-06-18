import os

import pytest
from pydantic import ValidationError

from shared.config import Settings


def test_settings_loads_from_env(monkeypatch):
    env = {
        "telegram_token": "test-token",
        "postgres_url": "postgresql://user:pass@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "ollama_base_url": "http://localhost:11434",
        "comfyui_base_url": "http://localhost:8188",
        "breezyvoice_base_url": "http://localhost:8080",
        "embedding_model": "BAAI/bge-m3",
        "model_name": "test-model",
        "log_level": "DEBUG",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    s = Settings()
    assert s.telegram_token == "test-token"
    assert s.log_level == "DEBUG"


def test_settings_accepts_breezyvoice_url_alias(monkeypatch):
    env = {
        "telegram_token": "test-token",
        "postgres_url": "postgresql://user:pass@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "ollama_base_url": "http://localhost:11434",
        "comfyui_base_url": "http://localhost:8188",
        "BREEZYVOICE_URL": "https://breezyvoice.momooai.com",
        "BREEZYVOICE_TOKEN": "secret-token",
        "embedding_model": "BAAI/bge-m3",
        "model_name": "test-model",
    }
    for key in ["breezyvoice_base_url", "BREEZYVOICE_BASE_URL"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    s = Settings()
    assert s.breezyvoice_base_url == "https://breezyvoice.momooai.com"
    assert s.breezyvoice_token == "secret-token"


def test_settings_ignores_empty_breezyvoice_alias_values(monkeypatch):
    env = {
        "telegram_token": "test-token",
        "postgres_url": "postgresql://user:pass@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "ollama_base_url": "http://localhost:11434",
        "comfyui_base_url": "http://localhost:8188",
        "breezyvoice_base_url": "",
        "BREEZYVOICE_URL": "https://breezyvoice.momooai.com",
        "breezyvoice_token": "",
        "BREEZYVOICE_TOKEN": "secret-token",
        "embedding_model": "BAAI/bge-m3",
        "model_name": "test-model",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    s = Settings()
    assert s.breezyvoice_base_url == "https://breezyvoice.momooai.com"
    assert s.breezyvoice_token == "secret-token"


def test_settings_missing_required_raises(monkeypatch):
    # Clear all application env vars.
    for key in [
        "telegram_token",
        "postgres_url",
        "redis_url",
        "ollama_base_url",
        "comfyui_base_url",
        "breezyvoice_base_url",
        "embedding_model",
        "model_name",
    ]:
        monkeypatch.delenv(key, raising=False)

    # Ensure no .env file is read by pointing env_file to a nonexistent path.
    class TestSettings(Settings):
        model_config = Settings.model_config.copy()
        model_config["env_file"] = ".env.does.not.exist"

    with pytest.raises(ValidationError):
        TestSettings()
