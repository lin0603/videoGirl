import asyncio

import pytest

import shared.llm as llm


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _FakeClient:
    """Stand-in for httpx.AsyncClient that records the last request."""

    reply: dict = {}
    last: dict = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _FakeClient.last = {"url": url, "json": json, "headers": headers}
        return _FakeResp(_FakeClient.reply)


@pytest.fixture(autouse=True)
def _reset():
    llm.reload()
    yield
    llm.reload()


def test_default_profile_is_ollama():
    client = llm.get_llm_client()
    assert isinstance(client, llm.OllamaProvider)
    assert client.profile.provider == "ollama"


def test_unknown_profile_raises():
    with pytest.raises(llm.LLMError):
        llm.get_llm_client("does-not-exist")


async def test_ollama_chat_parses_content(monkeypatch):
    _FakeClient.reply = {"message": {"content": "哈囉～"}}
    monkeypatch.setattr(llm.httpx, "AsyncClient", _FakeClient)
    out = await llm.get_llm_client("mac-qwen9b").chat(
        [{"role": "user", "content": "嗨"}]
    )
    assert out == "哈囉～"
    assert _FakeClient.last["url"].endswith("/api/chat")
    body = _FakeClient.last["json"]
    assert body["stream"] is False
    assert body["think"] is False  # girlfriend reply, not <think>


async def test_openai_compatible_chat_parses_content(monkeypatch):
    _FakeClient.reply = {"choices": [{"message": {"content": "hi"}}]}
    monkeypatch.setattr(llm.httpx, "AsyncClient", _FakeClient)
    out = await llm.get_llm_client("kimi").chat([{"role": "user", "content": "x"}])
    assert out == "hi"
    assert _FakeClient.last["url"].endswith("/chat/completions")
    # kimi preset must send the coding-agent User-Agent
    assert _FakeClient.last["headers"]["User-Agent"] == "claude-code/1.0"


async def test_chat_retries_then_raises(monkeypatch):
    async def _no_sleep(*_):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", _no_sleep)
    calls = {"n": 0}

    async def boom(self, messages, opts):
        calls["n"] += 1
        raise RuntimeError("down")

    monkeypatch.setattr(llm.OllamaProvider, "_once", boom)
    client = llm.get_llm_client("mac-qwen9b")
    with pytest.raises(llm.LLMError):
        await client.chat([{"role": "user", "content": "x"}])
    assert calls["n"] == client.max_retries
