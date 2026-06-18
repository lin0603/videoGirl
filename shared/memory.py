"""Memory system: conversation history + pgvector long-term memory + user dossier.

Public API used by the orchestrator:
- save_turn / get_recent_history       -> short-term conversation window
- retrieve_memories / build_memory_context -> long-term recall injected into prompt
- extract_and_store                    -> background fact/dossier extraction per turn
"""

from __future__ import annotations

import json

from shared.db import db
from shared.embeddings import get_embedder, to_pgvector
from shared.llm import LLMError, get_llm_client
from shared.logging import get_logger

log = get_logger("memory")

Message = dict[str, str]


def _estimate_tokens(text: str) -> int:
    # Rough: CJW-heavy text ~ 1 token per char is conservative enough for budgeting.
    return max(1, len(text))


async def save_turn(uid: int, role: str, content: str) -> None:
    await db.execute(
        "INSERT INTO conversation_turns (telegram_id, role, content, tokens_estimate) "
        "VALUES ($1, $2, $3, $4)",
        uid,
        role,
        content,
        _estimate_tokens(content),
    )


async def get_recent_history(uid: int, max_tokens: int = 1500) -> list[Message]:
    rows = await db.fetch(
        "SELECT role, content, tokens_estimate FROM conversation_turns "
        "WHERE telegram_id = $1 AND role IN ('user','assistant') "
        "ORDER BY created_at DESC LIMIT 50",
        uid,
    )
    picked: list[Message] = []
    budget = max_tokens
    for r in rows:  # newest first
        budget -= r["tokens_estimate"]
        if budget < 0:
            break
        picked.append({"role": r["role"], "content": r["content"]})
    picked.reverse()  # back to chronological order
    return picked


async def retrieve_memories(uid: int, query: str, top_k: int = 5) -> list[str]:
    try:
        vec = to_pgvector(await get_embedder().embed_one(query))
    except Exception as e:  # noqa: BLE001 - embeddings optional; degrade to no recall
        log.warning("embed_query_failed", error=str(e))
        return []
    rows = await db.fetch(
        "SELECT id, content FROM memories "
        "WHERE telegram_id = $1 AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2::vector LIMIT $3",
        uid,
        vec,
        top_k,
    )
    if rows:
        await db.execute(
            "UPDATE memories SET last_accessed = now() WHERE id = ANY($1::uuid[])",
            [r["id"] for r in rows],
        )
    return [r["content"] for r in rows]


async def get_dossier(uid: int) -> str:
    p = await db.fetchrow(
        "SELECT traits, preferences, life_facts, summary FROM user_profile WHERE telegram_id = $1",
        uid,
    )
    if not p:
        return ""
    parts: list[str] = []
    if p["summary"]:
        parts.append(p["summary"])
    for label, key in (("個性", "traits"), ("偏好", "preferences"), ("生活", "life_facts")):
        items = json.loads(p[key]) if isinstance(p[key], str) else p[key]
        if items:
            parts.append(f"{label}:{'、'.join(items)}")
    return "\n".join(parts)


async def build_memory_context(uid: int, query: str) -> str:
    dossier = await get_dossier(uid)
    recalled = await retrieve_memories(uid, query)
    blocks: list[str] = []
    if dossier:
        blocks.append(dossier)
    if recalled:
        blocks.append("相關記憶:" + "；".join(recalled))
    return "\n".join(blocks)


_EXTRACT_SYS = (
    "你是資訊抽取器。從對話中抽出關於『使用者』的長期資訊,只輸出 JSON,不要其他文字。"
    '格式:{"facts":[],"preferences":[],"traits":[],"life_facts":[],"dates":[]}。'
    "facts=具體事實;preferences=喜好;traits=個性特質;life_facts=生活/帳單/工作/作息;"
    "dates=生日紀念日等(格式『描述:MM-DD』)。沒有就給空陣列。用繁體中文。"
)


def _parse_json_obj(text: str) -> dict:
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j == -1:
        return {}
    try:
        return json.loads(text[i : j + 1])
    except json.JSONDecodeError:
        return {}


def _merge_unique(existing: list[str], new: list[str]) -> list[str]:
    seen = set(existing)
    return existing + [x for x in new if isinstance(x, str) and x and x not in seen]


async def extract_and_store(uid: int, snippet: str) -> None:
    """LLM-extract durable facts from a conversation snippet; upsert memory + dossier.

    Designed to run as a background task (does not block the reply).
    """
    try:
        raw = await get_llm_client().chat(
            [
                {"role": "system", "content": _EXTRACT_SYS},
                {"role": "user", "content": snippet},
            ],
            temperature=0,
            max_tokens=400,
        )
    except LLMError as e:
        log.warning("extract_llm_failed", error=str(e))
        return

    data = _parse_json_obj(raw)
    if not data:
        return

    # 1) durable "facts" -> embedded memories for semantic recall
    fact_items = [*data.get("facts", []), *data.get("dates", [])]
    embedder = get_embedder()
    for content in fact_items:
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            vec = to_pgvector(await embedder.embed_one(content))
        except Exception as e:  # noqa: BLE001
            log.warning("embed_fact_failed", error=str(e))
            continue
        await db.execute(
            "INSERT INTO memories (telegram_id, content, memory_type, embedding) "
            "VALUES ($1, $2, $3, $4::vector)",
            uid,
            content,
            "fact",
            vec,
        )

    # 2) traits/preferences/life_facts -> queryable dossier (merge, dedupe)
    existing = await db.fetchrow(
        "SELECT traits, preferences, life_facts FROM user_profile WHERE telegram_id = $1",
        uid,
    )

    def cur(key):
        if not existing:
            return []
        v = existing[key]
        return json.loads(v) if isinstance(v, str) else list(v)

    traits = _merge_unique(cur("traits"), data.get("traits", []))
    prefs = _merge_unique(cur("preferences"), data.get("preferences", []))
    facts = _merge_unique(cur("life_facts"), data.get("life_facts", []))
    await db.execute(
        """
        INSERT INTO user_profile (telegram_id, traits, preferences, life_facts, updated_at)
        VALUES ($1, $2::jsonb, $3::jsonb, $4::jsonb, now())
        ON CONFLICT (telegram_id) DO UPDATE
        SET traits = EXCLUDED.traits,
            preferences = EXCLUDED.preferences,
            life_facts = EXCLUDED.life_facts,
            updated_at = now()
        """,
        uid,
        json.dumps(traits, ensure_ascii=False),
        json.dumps(prefs, ensure_ascii=False),
        json.dumps(facts, ensure_ascii=False),
    )
    log.info("memory_extracted", uid=uid, facts=len(fact_items), traits=len(traits))
