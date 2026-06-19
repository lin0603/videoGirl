"""把長回覆拆成數則短訊息，並以防洪水（flood-safe）方式依序傳送。

用於：
- 一般聊天回覆：拆成 2～3 則短訊，像真人連續傳訊息。
- NSFW 主動撩撥：拆成 3～5 則短訊依序送出。
"""
from __future__ import annotations

import asyncio
import math
import re
from typing import Any

from shared.logging import get_logger

log = get_logger("shared.messaging")

_SENT_RE = re.compile(r"[^。！？!?…～\n]*[。！？!?…～]+|[^。！？!?…～\n]+$")


def _merge(items: list[str], n: int) -> list[str]:
    """把 items 合併成最多 n 組（每組數量大致相等）。"""
    if len(items) <= n:
        return items
    size = math.ceil(len(items) / n)
    return ["".join(items[i : i + size]).strip() for i in range(0, len(items), size)]


def split_into_bubbles(text: str, max_parts: int = 3) -> list[str]:
    """把文字拆成最多 max_parts 則訊息泡泡。

    優先用既有換行切；沒有換行就用句末標點切句，再合併成 max_parts 組。
    """
    text = (text or "").strip()
    if not text:
        return []
    lines = [ln.strip() for ln in re.split(r"\n+", text) if ln.strip()]
    if len(lines) >= 2:
        return [b for b in _merge(lines, max_parts) if b]
    sents = [s.strip() for s in _SENT_RE.findall(text) if s.strip()]
    if len(sents) <= 1:
        return [text]
    return [b for b in _merge(sents, max_parts) if b]


async def _safe_send(bot: Any, chat_id: int, text: str, retries: int = 2) -> None:
    """送一則訊息，遇到 Telegram flood（RetryAfter）就等待後重試。"""
    from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

    for attempt in range(retries + 1):
        try:
            await bot.send_message(chat_id, text)
            return
        except TelegramRetryAfter as exc:  # 觸發洪水限制
            await asyncio.sleep(exc.retry_after + 0.5)
        except TelegramBadRequest as exc:
            log.warning("send_bad_request", chat_id=chat_id, error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("send_failed", chat_id=chat_id, error=str(exc))
            return


async def send_bubbles(
    bot: Any,
    chat_id: int,
    text: str,
    *,
    max_parts: int = 3,
    base_delay: float = 0.6,
    typing: bool = True,
) -> list[str]:
    """把 text 拆成 max_parts 則短訊，依序（帶 typing 效果與間隔）送出。回傳實際送出的泡泡。"""
    bubbles = split_into_bubbles(text, max_parts)
    for i, bubble in enumerate(bubbles):
        if i > 0:
            if typing:
                try:
                    await bot.send_chat_action(chat_id, "typing")
                except Exception:  # noqa: BLE001
                    pass
            # 依長度給一點打字延遲，最多 ~1.4 秒，避免太像機器人也避免洪水
            await asyncio.sleep(min(1.4, base_delay + len(bubble) / 50.0))
        await _safe_send(bot, chat_id, bubble)
    return bubbles
