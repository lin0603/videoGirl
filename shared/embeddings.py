"""Switchable embedding client (mirrors shared/llm.py).

Default backend = Ollama running bge-m3 (dim 1024). The abstraction lets us
swap to a CPU embedder (e.g. fastembed) on the Coolify box later without
touching call sites.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

import httpx

from shared.config import get_settings

EMBED_DIM = 1024  # bge-m3


class Embedder(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]


class OllamaEmbedder(Embedder):
    def __init__(self, base_url: str, model: str, timeout: float = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for text in texts:
                r = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
                r.raise_for_status()
                out.append(r.json()["embedding"])
        return out


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    s = get_settings()
    # bge-m3 in Ollama is tagged "bge-m3" regardless of the HF-style name in config.
    model = s.embedding_model.split("/")[-1].lower() if "/" in s.embedding_model else s.embedding_model
    return OllamaEmbedder(s.ollama_base_url, model, timeout=s.llm_timeout_secs)


def to_pgvector(vec: list[float]) -> str:
    """Format a float list as a pgvector literal for `$n::vector` binding."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
