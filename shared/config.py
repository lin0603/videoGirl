from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    telegram_token: str
    postgres_url: str
    redis_url: str
    ollama_base_url: str
    comfyui_base_url: str
    breezyvoice_base_url: str = Field(
        validation_alias=AliasChoices(
            "breezyvoice_base_url",
            "BREEZYVOICE_BASE_URL",
            "BREEZYVOICE_URL",
        )
    )
    breezyvoice_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "breezyvoice_token",
            "BREEZYVOICE_TOKEN",
        ),
    )
    embedding_model: str
    model_name: str
    log_level: str = "INFO"

    # --- Switchable LLM backends (see shared/llm.py) ---
    # Active profile name from the registry in shared/llm.py.
    llm_profile: str = "mac-qwen9b"
    llm_timeout_secs: int = 120
    llm_max_retries: int = 3
    # Optional OpenAI-compatible backend (vLLM on 4090 / Kimi / OpenRouter).
    # Filled only when you switch llm_profile to one that uses it.
    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    openai_compat_model: str = ""
    vllm_base_url: str = ""

    # --- Admin web UI (task #7) ---
    admin_username: str = "admin"
    admin_password: str = "admin"
    admin_secret_key: str = "change-me-in-production"
    admin_host: str = "0.0.0.0"
    admin_port: int = 8000

    # --- VIP subscription (task #21) ---
    vip_amount_stars: int = 199
    vip_subscription_period_seconds: int = 2592000  # 30 days
    vip_grace_period_seconds: int = 259200  # 3 days
    # Comma-separated Telegram user ids allowed to run admin bot commands
    # (e.g. /refund_stars). Empty = nobody (refunds disabled via bot).
    admin_telegram_ids: str = ""

    # --- Telegram Mini App public surface (tasks #27-#30) ---
    mini_app_allowed_origins: str = "*"
    mini_app_init_data_max_age_seconds: int = 86400


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def __getattr__(name: str):
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
