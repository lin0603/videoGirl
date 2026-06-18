"""Orchestrator core (task #6, lite).

Wires persona + (later) memory + history into the switchable LLM client and
returns a reply string. Telegram I/O (task #2) and memory (task #5) plug in
around this.
"""

from __future__ import annotations

from shared.llm import LLMError, get_llm_client
from shared.logging import get_logger

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
) -> str:
    """Build the prompt and get an in-character reply. Degrades on LLM failure."""
    messages: list[Message] = [
        {
            "role": "system",
            "content": build_system_prompt(
                persona, memory_context=memory, nsfw_enabled=nsfw
            ),
        }
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        return await get_llm_client().chat(messages, max_tokens=400)
    except LLMError as e:
        log.warning("generate_reply_fallback", error=str(e))
        return FALLBACK_REPLY


async def _demo() -> None:
    import sys

    persona = get_persona()
    nsfw = "--nsfw" in sys.argv
    print(f"與「{persona.name}」對話中(輸入 exit 離開)。nsfw={nsfw}\n")
    history: list[Message] = []
    loop = __import__("asyncio").get_event_loop()
    while True:
        try:
            user_text = await loop.run_in_executor(None, input, "你> ")
        except (EOFError, KeyboardInterrupt):
            break
        if user_text.strip() in {"exit", "quit"}:
            break
        reply = await generate_reply(
            persona, user_text, nsfw=nsfw, history=history[-8:]
        )
        print(f"{persona.name}> {reply}\n")
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":  # python -m orchestrator.core --demo [--nsfw]
    import asyncio
    import sys

    if "--demo" in sys.argv:
        asyncio.run(_demo())
    else:
        print("usage: python -m orchestrator.core --demo [--nsfw]")
