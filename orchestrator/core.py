"""Orchestrator core (tasks #6 + #5 wiring).

`generate_reply` stays a pure persona+LLM function. `respond` adds the memory
layer (history + dossier/recall + background extraction) and is what the
Telegram bot (#2) calls.
"""

from __future__ import annotations

import asyncio

from shared.llm import LLMError, get_llm_client
from shared.logging import get_logger
from shared.memory import (
    build_memory_context,
    extract_and_store,
    get_recent_history,
    save_turn,
)

from orchestrator.persona import Persona, build_system_prompt, get_persona

log = get_logger("orchestrator")

Message = dict[str, str]

FALLBACK_REPLY = "嗯…我這邊有點恍神,可以再跟我說一次嗎?(´；ω；`)"


async def generate_reply(
    persona: Persona,
    user_text: str,
    *,
    nsfw: bool = False,
    history: list[Message] | None = None,
    memory: str = "",
    mood_context: str = "",
    intimacy_context: str = "",
) -> str:
    """Build the prompt and get an in-character reply. Degrades on LLM failure."""
    style = (
        "\n\n【回覆風格】像在用手機傳訊息給戀人：簡短、口語、有感情。"
        "整體長度約是平常的三分之一（大約 30～70 字），不要長篇大論。"
        "可以用換行把回覆拆成 2～3 則很短的訊息（像連續傳訊息那樣），每則一兩句即可。"
        "動作或神情描述若有，請放在括號內。"
    )
    messages: list[Message] = [
        {
            "role": "system",
            "content": build_system_prompt(
                persona,
                memory_context=memory,
                mood_context=mood_context,
                intimacy_context=intimacy_context,
                nsfw_enabled=nsfw,
            ) + style,
        }
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        return await get_llm_client().chat(messages, max_tokens=200)
    except LLMError as e:
        log.warning("generate_reply_fallback", error=str(e))
        return FALLBACK_REPLY


async def respond(
    uid: int,
    user_text: str,
    persona: Persona,
    *,
    nsfw: bool = False,
    mood_context: str = "",
    intimacy_context: str = "",
) -> str:
    """Full memory-aware turn: recall -> reply -> persist -> background-extract."""
    history = await get_recent_history(uid)
    memory = await build_memory_context(uid, user_text)
    reply = await generate_reply(
        persona,
        user_text,
        nsfw=nsfw,
        history=history,
        memory=memory,
        mood_context=mood_context,
        intimacy_context=intimacy_context,
    )
    await save_turn(uid, "user", user_text)
    await save_turn(uid, "assistant", reply)
    snippet = f"使用者:{user_text}\n女友:{reply}"
    asyncio.create_task(extract_and_store(uid, snippet))  # don't block the reply
    return reply


async def _demo(use_memory: bool, nsfw: bool) -> None:
    persona = get_persona()
    uid = 999999  # demo user
    if use_memory:
        from shared.db import db

        await db.connect()
        await db.execute(
            "INSERT INTO users (telegram_id, display_name, nsfw_opt_in) "
            "VALUES ($1,'demo',$2) ON CONFLICT (telegram_id) DO NOTHING",
            uid,
            nsfw,
        )
    print(f"與「{persona.name}」對話中(exit 離開)。memory={use_memory} nsfw={nsfw}\n")
    history: list[Message] = []
    loop = asyncio.get_event_loop()
    try:
        while True:
            user_text = await loop.run_in_executor(None, input, "你> ")
            if user_text.strip() in {"exit", "quit"}:
                break
            if use_memory:
                reply = await respond(uid, user_text, persona, nsfw=nsfw)
            else:
                reply = await generate_reply(
                    persona, user_text, nsfw=nsfw, history=history[-8:]
                )
                history += [
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": reply},
                ]
            print(f"{persona.name}> {reply}\n")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":  # python -m orchestrator.core --demo [--nsfw] [--no-memory]
    import sys

    if "--demo" in sys.argv:
        asyncio.run(
            _demo(use_memory="--no-memory" not in sys.argv, nsfw="--nsfw" in sys.argv)
        )
    else:
        print("usage: python -m orchestrator.core --demo [--nsfw] [--no-memory]")
