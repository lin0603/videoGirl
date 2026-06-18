"""Switchable LLM client.

A small provider abstraction so the LLM backend can be swapped via the
``LLM_PROFILE`` setting without touching call sites. Two providers cover every
backend we care about:

* ``OllamaProvider`` -> Mac mini Ollama (`/api/chat`)
* ``OpenAICompatibleProvider`` -> vLLM on the 4090 / Kimi / OpenRouter
  (`/v1/chat/completions`)

Call sites just use::

    from shared.llm import get_llm_client
    reply = await get_llm_client().chat(messages)

Switch backend by setting ``llm_profile`` (env ``LLM_PROFILE``) to a name in
``build_profiles()``.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache

import httpx

from shared.config import get_settings
from shared.logging import get_logger

log = get_logger("llm")

Message = dict[str, str]


class LLMError(RuntimeError):
    """Raised when the active backend cannot produce a reply (after retries).

    Orchestrator should catch this and degrade gracefully (e.g. fall back text).
    """


@dataclass(frozen=True)
class Profile:
    provider: str  # "ollama" | "openai"
    base_url: str
    model: str
    api_key: str | None = None
    params: dict = field(default_factory=dict)  # temperature, num_ctx, think, ...
    headers: dict = field(default_factory=dict)


def build_profiles(s) -> dict[str, Profile]:
    """Build the profile registry from settings (env-driven values)."""
    chat_defaults = {"temperature": 0.8, "num_ctx": 4096, "think": False}
    return {
        # Default: Mac mini Ollama, Qwen3.5-9B (Traditional-Chinese, uncensored).
        "mac-qwen9b": Profile(
            "ollama", s.ollama_base_url, s.model_name, params=dict(chat_defaults)
        ),
        "mac-gemma": Profile(
            "ollama", s.ollama_base_url, "gemma4:e4b", params=dict(chat_defaults)
        ),
        # 4090 vLLM (OpenAI-compatible). Set vllm_base_url + openai_compat_model.
        "4090-vllm": Profile(
            "openai",
            s.vllm_base_url,
            s.openai_compat_model,
            api_key=s.openai_compat_api_key or None,
            params={"temperature": 0.8},
        ),
        # Kimi Code (OpenAI-compatible). Needs a coding-agent User-Agent.
        "kimi": Profile(
            "openai",
            s.openai_compat_base_url or "https://api.kimi.com/coding/v1",
            s.openai_compat_model or "kimi-for-coding",
            api_key=s.openai_compat_api_key or None,
            params={"temperature": 1},
            headers={"User-Agent": "claude-code/1.0"},
        ),
        # OpenRouter (OpenAI-compatible).
        "openrouter": Profile(
            "openai",
            s.openai_compat_base_url or "https://openrouter.ai/api/v1",
            s.openai_compat_model,
            api_key=s.openai_compat_api_key or None,
            params={"temperature": 0.8},
        ),
    }


class LLMProvider(ABC):
    def __init__(self, profile: Profile, *, timeout: float, max_retries: int):
        self.profile = profile
        self.timeout = timeout
        self.max_retries = max_retries

    @abstractmethod
    async def _once(self, messages: list[Message], opts: dict) -> str:
        """Single attempt; raise on failure."""

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **opts,
    ) -> str:
        merged = {**self.profile.params, **opts}
        if temperature is not None:
            merged["temperature"] = temperature
        if max_tokens is not None:
            merged["max_tokens"] = max_tokens

        last: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            t0 = time.monotonic()
            try:
                text = await self._once(messages, merged)
                log.info(
                    "llm_reply",
                    profile=get_settings().llm_profile,
                    model=self.profile.model,
                    latency_s=round(time.monotonic() - t0, 2),
                    chars=len(text),
                )
                return text
            except Exception as e:  # noqa: BLE001 - retry any transport/HTTP error
                last = e
                log.warning("llm_attempt_failed", attempt=attempt, error=str(e))
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * 2 ** (attempt - 1))
        raise LLMError(
            f"{self.profile.provider}:{self.profile.model} failed after "
            f"{self.max_retries} attempts: {last}"
        ) from last


class OllamaProvider(LLMProvider):
    async def _once(self, messages: list[Message], opts: dict) -> str:
        think = opts.pop("think", False)
        options = {k: opts[k] for k in ("temperature", "num_ctx", "num_predict") if k in opts}
        if "max_tokens" in opts:
            options["num_predict"] = opts["max_tokens"]
        body = {
            "model": self.profile.model,
            "messages": messages,
            "stream": False,
            "think": think,
            "options": options,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.profile.base_url.rstrip('/')}/api/chat",
                json=body,
                headers=self.profile.headers or None,
            )
            r.raise_for_status()
            return r.json()["message"]["content"]


class OpenAICompatibleProvider(LLMProvider):
    async def _once(self, messages: list[Message], opts: dict) -> str:
        body: dict = {"model": self.profile.model, "messages": messages}
        if "temperature" in opts:
            body["temperature"] = opts["temperature"]
        if opts.get("max_tokens"):
            body["max_tokens"] = opts["max_tokens"]
        headers = dict(self.profile.headers)
        if self.profile.api_key:
            headers["Authorization"] = f"Bearer {self.profile.api_key}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.profile.base_url.rstrip('/')}/chat/completions"
                if self.profile.base_url.rstrip("/").endswith("/v1")
                else f"{self.profile.base_url.rstrip('/')}/v1/chat/completions",
                json=body,
                headers=headers or None,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


_PROVIDERS = {"ollama": OllamaProvider, "openai": OpenAICompatibleProvider}


@lru_cache(maxsize=None)
def _client_for(profile_name: str) -> LLMProvider:
    s = get_settings()
    profiles = build_profiles(s)
    if profile_name not in profiles:
        raise LLMError(
            f"unknown LLM profile {profile_name!r}; known: {sorted(profiles)}"
        )
    p = profiles[profile_name]
    if not p.base_url:
        raise LLMError(f"profile {profile_name!r} has no base_url configured")
    return _PROVIDERS[p.provider](
        p, timeout=s.llm_timeout_secs, max_retries=s.llm_max_retries
    )


def get_llm_client(profile: str | None = None) -> LLMProvider:
    """Return the client for the active profile (or an explicit override)."""
    return _client_for(profile or get_settings().llm_profile)


def reload() -> None:
    """Clear cached clients so a changed profile/config takes effect."""
    _client_for.cache_clear()


async def _smoke() -> None:
    client = get_llm_client()
    p = client.profile
    print(f"profile={get_settings().llm_profile} provider={p.provider} model={p.model} base={p.base_url}")
    t0 = time.monotonic()
    reply = await client.chat(
        [
            {"role": "system", "content": "你是溫柔的女友,只用繁體中文(台灣用語)回覆。"},
            {"role": "user", "content": "我今天上班好累喔"},
        ],
        max_tokens=200,
    )
    print(f"reply ({time.monotonic() - t0:.1f}s):\n{reply}")


if __name__ == "__main__":  # `python -m shared.llm --test`
    import sys

    if "--test" in sys.argv:
        asyncio.run(_smoke())
    else:
        print("usage: python -m shared.llm --test")
