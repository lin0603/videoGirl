"""Telegram Stars VIP subscription service."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import LabeledPrice, PreCheckoutQuery, SuccessfulPayment
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.logging import get_logger
from shared.repositories.subscription_repo import SubscriptionRepository

logger = get_logger("shared.subscriptions")

STARS_CURRENCY = "XTR"
STARS_PROVIDER_TOKEN = ""
VIP_PRODUCT_SLUG = "vip_monthly"
VIP_PAYLOAD_PREFIX = "stars:sub:vip_monthly:"


class SubscriptionValidationError(ValueError):
    pass


def is_vip_payload(payload: str) -> bool:
    return payload.startswith(VIP_PAYLOAD_PREFIX)


def build_vip_payload() -> str:
    return f"{VIP_PAYLOAD_PREFIX}{secrets.token_urlsafe(18)}"


async def create_invoice_link(bot: Bot, user_id: int) -> str:
    settings = get_settings()
    period_seconds = settings.vip_subscription_period_seconds
    payload = build_vip_payload()
    logger.info("vip_invoice_link_creating", user_id=user_id)
    return await bot.create_invoice_link(
        title="VIP 月訂閱",
        description="解鎖無限聊天、NSFW 內容與更高媒體配額。每月自動續訂。",
        payload=payload,
        provider_token=STARS_PROVIDER_TOKEN,
        currency=STARS_CURRENCY,
        prices=[LabeledPrice(label="VIP 月訂閱", amount=settings.vip_amount_stars)],
        subscription_period=period_seconds,
    )


async def validate_pre_checkout(query: PreCheckoutQuery) -> None:
    settings = get_settings()
    if not is_vip_payload(query.invoice_payload):
        raise SubscriptionValidationError("無效的訂閱發票。")
    if query.currency != STARS_CURRENCY:
        raise SubscriptionValidationError("付款幣別不正確。")
    if query.total_amount != settings.vip_amount_stars:
        raise SubscriptionValidationError("付款金額不正確。")


async def handle_successful_payment(
    session: AsyncSession,
    user_id: int,
    payment: SuccessfulPayment,
) -> tuple[SubscriptionRepository, bool]:
    """Upsert subscription from a successful Stars subscription payment.

    Returns (repo, is_new) where is_new indicates a fresh activation/extension.
    """
    if not is_vip_payload(payment.invoice_payload):
        raise SubscriptionValidationError("不是 VIP 訂閱發票。")

    settings = get_settings()
    repo = SubscriptionRepository(session)

    # Telegram passes the subscription expiration date as a Unix timestamp.
    if payment.subscription_expiration_date:
        period_end = datetime.fromtimestamp(
            payment.subscription_expiration_date, tz=timezone.utc
        )
    else:
        period_end = datetime.now(timezone.utc) + timedelta(
            seconds=settings.vip_subscription_period_seconds
        )

    existing = await repo.get_active(user_id)
    is_new = existing is None

    sub = await repo.create_or_extend(
        user_id=user_id,
        current_period_end=period_end,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
        provider_payment_charge_id=payment.provider_payment_charge_id,
    )
    logger.info(
        "vip_subscription_activated_or_extended",
        user_id=user_id,
        subscription_id=sub.id,
        period_end=period_end.isoformat(),
        is_new=is_new,
    )
    return repo, is_new


async def cancel_subscription(session: AsyncSession, user_id: int) -> bool:
    repo = SubscriptionRepository(session)
    sub = await repo.cancel(user_id)
    if sub is None:
        return False
    logger.info("vip_subscription_cancelled", user_id=user_id, subscription_id=sub.id)
    return True
