"""
Referral attribution + deep-link funnel (task #23).

Deep-link formats:
  /start ref<referrer_id>          — referred by a user
  /start src_<campaign>            — campaign attribution (no referrer reward)
  /start ref<referrer_id>_<source> — both
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger
from shared.models import Referral

log = get_logger("referral")

# Reward (credits) granted to the referrer when referred user activates.
_DEFAULT_REFERRAL_REWARD = 20


@dataclass
class StartPayload:
    referrer_id: int | None
    source: str | None  # campaign slug, e.g. "channel", "web"


def parse_start_payload(text: str) -> StartPayload:
    """
    Parse the argument from a /start deep-link.

    Examples:
      "ref123456789"         → referrer_id=123456789, source=None
      "src_channel"          → referrer_id=None, source="channel"
      "ref123456789_channel" → referrer_id=123456789, source="channel"
      ""                     → referrer_id=None, source=None
    """
    referrer_id: int | None = None
    source: str | None = None

    m = re.match(r"ref(\d+)(?:_(.+))?$", text or "")
    if m:
        referrer_id = int(m.group(1))
        source = m.group(2)
        return StartPayload(referrer_id=referrer_id, source=source)

    m = re.match(r"src_(.+)$", text or "")
    if m:
        source = m.group(1)

    return StartPayload(referrer_id=referrer_id, source=source)


def make_deep_link(bot_username: str, referrer_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref{referrer_id}"


async def record_referral(
    session: AsyncSession,
    *,
    referrer_id: int | None,
    referred_id: int,
    source: str | None,
) -> Referral | None:
    """
    Create a referral record if one doesn't exist yet for referred_id.
    Returns the Referral or None if already attributed.
    """
    existing = await session.get(Referral, referred_id)
    if existing is not None:
        return None  # already attributed

    ref = Referral(
        referrer_id=referrer_id,
        referred_id=referred_id,
        source=source,
    )
    session.add(ref)
    await session.commit()
    await session.refresh(ref)
    log.info("referral_recorded", referrer_id=referrer_id, referred_id=referred_id, source=source)
    return ref


async def maybe_grant_referral_reward(
    session: AsyncSession,
    referred_id: int,
    *,
    reward_credits: int = _DEFAULT_REFERRAL_REWARD,
) -> int | None:
    """
    Called when a referred user completes onboarding.
    If there's an unawarded referral, grants credits to the referrer.
    Returns referrer_id if reward was granted, else None.
    """
    result = await session.execute(
        select(Referral).where(
            Referral.referred_id == referred_id,
            Referral.referrer_id.isnot(None),
            Referral.reward_given_at.is_(None),
        )
    )
    ref = result.scalar_one_or_none()
    if ref is None:
        return None

    from shared.wallet import WalletService

    await WalletService(session).top_up(
        ref.referrer_id,
        reward_credits,
        reason="referral_reward",
        reference=str(referred_id),
    )
    ref.reward_given_at = datetime.utcnow()
    await session.commit()
    log.info(
        "referral_reward_granted",
        referrer_id=ref.referrer_id,
        referred_id=referred_id,
        credits=reward_credits,
    )
    return ref.referrer_id
