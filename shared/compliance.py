"""Compliance and payout-safety helpers (task #31).

Responsibilities:
- Fetch current Stars balance via Telegram API.
- Warn when balance reaches Fragment payout threshold (1,000 XTR).
- Audit NSFW exposure — confirm non-opted users never receive explicit content.
"""
from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot

from shared.logging import get_logger

logger = get_logger("compliance")

FRAGMENT_MIN_PAYOUT_XTR = 1_000
FRAGMENT_HOLD_DAYS = 21


@dataclass
class StarsStatus:
    balance: int
    payout_ready: bool  # True when balance >= FRAGMENT_MIN_PAYOUT_XTR
    message: str


async def get_stars_status(bot: Bot) -> StarsStatus:
    """
    Fetch the bot's current Stars (XTR) balance from Telegram.
    Returns a StarsStatus with human-readable status for admin display.
    """
    try:
        result = await bot.get_my_star_balance()
        balance = result.amount if hasattr(result, "amount") else int(result)
    except Exception as exc:
        logger.error("stars_balance_fetch_failed", error=str(exc))
        balance = -1

    payout_ready = balance >= FRAGMENT_MIN_PAYOUT_XTR

    if balance < 0:
        message = "無法取得餘額（API 錯誤）"
    elif payout_ready:
        message = (
            f"✅ 餘額 {balance} XTR — 已達提領門檻！\n"
            f"可至 Fragment 申請提領（最低 {FRAGMENT_MIN_PAYOUT_XTR} XTR，{FRAGMENT_HOLD_DAYS} 天鎖定）。"
        )
    else:
        needed = FRAGMENT_MIN_PAYOUT_XTR - balance
        message = (
            f"💰 餘額 {balance} XTR\n"
            f"距提領門檻還差 {needed} XTR。"
        )

    if payout_ready:
        logger.info("payout_threshold_reached", balance=balance)

    return StarsStatus(balance=balance, payout_ready=payout_ready, message=message)
