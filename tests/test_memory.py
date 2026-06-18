import json

import pytest

import shared.memory as mem


class FakeDB:
    def __init__(self, fetch_rows=None, fetchrow_row=None):
        self._fetch_rows = fetch_rows or []
        self._fetchrow_row = fetchrow_row
        self.executed: list[tuple] = []

    async def fetch(self, query, *args):
        return self._fetch_rows

    async def fetchrow(self, query, *args):
        return self._fetchrow_row

    async def execute(self, query, *args):
        self.executed.append((query, args))


class FakeEmbedder:
    async def embed_one(self, text):
        return [0.1] * 8

    async def embed(self, texts):
        return [[0.1] * 8 for _ in texts]


async def test_recent_history_respects_token_budget(monkeypatch):
    rows = [  # newest first (as the SQL returns)
        {"role": "assistant", "content": "c", "tokens_estimate": 10},
        {"role": "user", "content": "b", "tokens_estimate": 10},
        {"role": "assistant", "content": "a", "tokens_estimate": 10},
    ]
    monkeypatch.setattr(mem, "db", FakeDB(fetch_rows=rows))
    hist = await mem.get_recent_history(1, max_tokens=15)  # only 1 turn fits
    assert hist == [{"role": "assistant", "content": "c"}]


async def test_build_memory_context_formats(monkeypatch):
    profile = {
        "traits": json.dumps(["溫柔"], ensure_ascii=False),
        "preferences": json.dumps(["咖啡"], ensure_ascii=False),
        "life_facts": json.dumps(["每月15號電費"], ensure_ascii=False),
        "summary": "阿明,工程師",
    }
    db = FakeDB(fetch_rows=[{"id": "x", "content": "養了一隻貓"}], fetchrow_row=profile)
    monkeypatch.setattr(mem, "db", db)
    monkeypatch.setattr(mem, "get_embedder", lambda: FakeEmbedder())
    ctx = await mem.build_memory_context(1, "你還記得我嗎")
    assert "阿明" in ctx and "咖啡" in ctx and "每月15號電費" in ctx
    assert "相關記憶" in ctx and "養了一隻貓" in ctx


async def test_extract_and_store_parses_and_upserts(monkeypatch):
    db = FakeDB(fetchrow_row=None)  # no existing profile
    monkeypatch.setattr(mem, "db", db)
    monkeypatch.setattr(mem, "get_embedder", lambda: FakeEmbedder())

    class FakeLLM:
        async def chat(self, messages, **kw):
            return (
                '前言{"facts":["養了一隻貓"],"preferences":["咖啡"],'
                '"traits":["溫柔"],"life_facts":["每月15號電費"],"dates":["生日:03-05"]}尾巴'
            )

    monkeypatch.setattr(mem, "get_llm_client", lambda *a, **k: FakeLLM())
    await mem.extract_and_store(1, "使用者:我養貓,每月15號繳電費,生日3月5號")

    joined = " ".join(q for q, _ in db.executed)
    assert "INSERT INTO memories" in joined  # facts + dates embedded
    assert "INSERT INTO user_profile" in joined  # dossier upsert
    # the upsert carries merged traits/prefs/life_facts as JSON
    upsert = [a for q, a in db.executed if "user_profile" in q][0]
    assert any("溫柔" in str(x) for x in upsert)
