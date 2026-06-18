import orchestrator.core as core
import shared.llm as llm
from orchestrator.core import FALLBACK_REPLY, generate_reply
from orchestrator.persona import get_persona


class _FakeClient:
    captured: list = []

    async def chat(self, messages, **kwargs):
        _FakeClient.captured = messages
        return "嗨～親愛的"


class _BoomClient:
    async def chat(self, messages, **kwargs):
        raise llm.LLMError("backend down")


async def test_generate_reply_builds_persona_prompt(monkeypatch):
    monkeypatch.setattr(core, "get_llm_client", lambda *a, **k: _FakeClient())
    p = get_persona("xiaorou")
    out = await generate_reply(p, "嗨", nsfw=True)
    assert out == "嗨～親愛的"
    system = _FakeClient.captured[0]
    assert system["role"] == "system"
    assert p.name in system["content"]
    assert "成人模式" in system["content"]  # nsfw flag propagated
    assert _FakeClient.captured[-1] == {"role": "user", "content": "嗨"}


async def test_generate_reply_degrades_on_llm_error(monkeypatch):
    monkeypatch.setattr(core, "get_llm_client", lambda *a, **k: _BoomClient())
    out = await generate_reply(get_persona("xiaorou"), "在嗎")
    assert out == FALLBACK_REPLY


async def test_respond_wires_memory_and_persists(monkeypatch):
    saved: list = []

    async def fake_history(uid, **k):
        return [{"role": "user", "content": "先前訊息"}]

    async def fake_context(uid, query):
        return "記憶:使用者叫阿明"

    async def fake_save(uid, role, content):
        saved.append((role, content))

    async def fake_extract(uid, snippet):
        return None

    monkeypatch.setattr(core, "get_llm_client", lambda *a, **k: _FakeClient())
    monkeypatch.setattr(core, "get_recent_history", fake_history)
    monkeypatch.setattr(core, "build_memory_context", fake_context)
    monkeypatch.setattr(core, "save_turn", fake_save)
    monkeypatch.setattr(core, "extract_and_store", fake_extract)

    out = await core.respond(1, "嗨", get_persona("xiaorou"), nsfw=False)
    assert out == "嗨～親愛的"
    msgs = _FakeClient.captured
    assert "記憶:使用者叫阿明" in msgs[0]["content"]  # memory injected into system
    assert {"role": "user", "content": "先前訊息"} in msgs  # history included
    assert saved == [("user", "嗨"), ("assistant", "嗨～親愛的")]
