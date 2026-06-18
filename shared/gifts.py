"""Virtual gift catalog and unlock service (task #22).

Gifts: user sends Stars → companion mood rises + warm in-character reaction.
Unlocks: user pays Stars → specific item_key is permanently accessible.

Payload format (matched in payments handler):
  gift:flower:abc123           → virtual gift
  unlock:photo_pack:abc123     → media unlock
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.types import LabeledPrice, SuccessfulPayment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import GiftRecord, Unlock

STARS_CURRENCY = "XTR"

_GIFT_PAYLOAD_PREFIX = "gift:"
_UNLOCK_PAYLOAD_PREFIX = "unlock:"


@dataclass(frozen=True)
class GiftItem:
    key: str
    emoji: str
    title: str
    description: str
    stars: int
    mood_boost: float


GIFT_CATALOG: dict[str, GiftItem] = {
    "flower": GiftItem(
        key="flower",
        emoji="🌹",
        title="送一束玫瑰花",
        description="送給女友一束玫瑰，她會很開心的！",
        stars=15,
        mood_boost=0.15,
    ),
    "cake": GiftItem(
        key="cake",
        emoji="🎂",
        title="送一個蛋糕",
        description="甜蜜的蛋糕，讓心情更美麗。",
        stars=30,
        mood_boost=0.25,
    ),
    "diamond": GiftItem(
        key="diamond",
        emoji="💎",
        title="送一顆鑽石",
        description="最閃耀的禮物，讓她知道你有多在乎。",
        stars=99,
        mood_boost=0.5,
    ),
}


def is_gift_payload(payload: str) -> bool:
    return payload.startswith(_GIFT_PAYLOAD_PREFIX)


def is_unlock_payload(payload: str) -> bool:
    return payload.startswith(_UNLOCK_PAYLOAD_PREFIX)


def parse_gift_key(payload: str) -> str | None:
    """Extract gift_key from 'gift:flower:nonce' payload."""
    parts = payload.split(":", 2)
    if len(parts) >= 2 and parts[0] == "gift":
        return parts[1]
    return None


def parse_unlock_key(payload: str) -> str | None:
    """Extract item_key from 'unlock:photo_pack:nonce' payload."""
    parts = payload.split(":", 2)
    if len(parts) >= 2 and parts[0] == "unlock":
        return parts[1]
    return None


async def create_gift_invoice(
    bot: Bot,
    chat_id: int,
    gift_key: str,
) -> str:
    """Send an invoice for the given gift and return the invoice link."""
    item = GIFT_CATALOG.get(gift_key)
    if item is None:
        raise ValueError(f"Unknown gift: {gift_key}")

    payload = f"gift:{gift_key}:{secrets.token_urlsafe(12)}"
    link = await bot.create_invoice_link(
        title=item.title,
        description=item.description,
        payload=payload,
        currency=STARS_CURRENCY,
        prices=[LabeledPrice(label=item.title, amount=item.stars)],
    )
    return link


async def create_unlock_invoice(
    bot: Bot,
    item_key: str,
    title: str,
    description: str,
    stars: int,
) -> str:
    """Send an invoice to unlock a specific item."""
    payload = f"unlock:{item_key}:{secrets.token_urlsafe(12)}"
    link = await bot.create_invoice_link(
        title=title,
        description=description,
        payload=payload,
        currency=STARS_CURRENCY,
        prices=[LabeledPrice(label=title, amount=stars)],
    )
    return link


async def record_gift(
    session: AsyncSession,
    sender_id: int,
    payment: SuccessfulPayment,
) -> tuple[GiftRecord, bool]:
    """Record a gift payment idempotently. Returns (record, is_new)."""
    charge_id = payment.telegram_payment_charge_id
    # Check for existing record first to avoid IntegrityError / session breakage.
    existing = (
        await session.execute(
            select(GiftRecord).where(GiftRecord.charge_id == charge_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    gift_key = parse_gift_key(payment.invoice_payload) or "unknown"
    item = GIFT_CATALOG.get(gift_key)
    mood_boost = item.mood_boost if item else 0.1

    record = GiftRecord(
        sender_id=sender_id,
        gift_key=gift_key,
        stars_paid=payment.total_amount,
        mood_boost=mood_boost,
        charge_id=charge_id,
        sent_at=datetime.utcnow(),
    )
    session.add(record)
    await session.flush()
    return record, True


async def record_unlock(
    session: AsyncSession,
    user_id: int,
    item_key: str,
    payment: SuccessfulPayment,
) -> tuple[Unlock, bool]:
    """Record a media unlock idempotently. Returns (record, is_new)."""
    charge_id = payment.telegram_payment_charge_id
    existing = (
        await session.execute(
            select(Unlock).where(Unlock.charge_id == charge_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    record = Unlock(
        user_id=user_id,
        item_key=item_key,
        stars_paid=payment.total_amount,
        charge_id=charge_id,
        unlocked_at=datetime.utcnow(),
    )
    session.add(record)
    await session.flush()
    return record, True


async def is_unlocked(session: AsyncSession, user_id: int, item_key: str) -> bool:
    """Return True if the user has unlocked this item."""
    result = await session.execute(
        select(Unlock.id).where(
            Unlock.user_id == user_id,
            Unlock.item_key == item_key,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None
