from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_token: str
    postgres_url: str
    redis_url: str
    ollama_base_url: str
    comfyui_base_url: str
    breezyvoice_base_url: str
    breezyvoice_token: str = ""
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

    # --- TTS (BreezyVoice, see shared/tts.py) ---
    tts_timeout_secs: int = 240
    tts_poll_secs: float = 4.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def __getattr__(name: str):
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
