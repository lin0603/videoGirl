"""Gacha photo pack system (task #25).

Rarity tiers:
  R   (Common)       — 70 % — selfie/portrait scenes
  SR  (Rare)         — 25 % — lingerie/intimate scenes
  SSR (Super Rare)   — 5 %  — most explicit scenes (NSFW-gated)

Pity: after 20 consecutive non-SSR draws, the next draw is guaranteed SSR.
Cost: 10 credits per draw (set in GACHA_COST_CREDITS).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.image_gen import request_photo
from shared.models import GachaDraw

GACHA_COST_CREDITS = 10
PITY_THRESHOLD = 20  # guarantee SSR after this many non-SSR draws


@dataclass(frozen=True)
class RarityTier:
    key: str       # "R", "SR", "SSR"
    label: str
    weight: int    # relative weight for random.choices
    scenes: list[str]


TIERS: list[RarityTier] = [
    RarityTier("R",   "✨ 普通",  70, ["selfie", "portrait", "casual"]),
    RarityTier("SR",  "💎 稀有",  25, ["swimsuit", "lingerie"]),
    RarityTier("SSR", "🌟 超稀有", 5, ["topless", "nsfw_full"]),
]

_TIER_MAP = {t.key: t for t in TIERS}
_WEIGHTS = [t.weight for t in TIERS]


def sample_rarity(*, force_ssr: bool = False) -> str:
    if force_ssr:
        return "SSR"
    return random.choices([t.key for t in TIERS], weights=_WEIGHTS, k=1)[0]


def sample_scene(rarity: str, *, nsfw: bool) -> str:
    tier = _TIER_MAP.get(rarity, TIERS[0])
    eligible = tier.scenes
    if not nsfw:
        eligible = [s for s in eligible if s not in ("topless", "nsfw_full")]
    if not eligible:
        eligible = TIERS[0].scenes
    return random.choice(eligible)


def odds_text() -> str:
    lines = [f"・{t.label}（{t.key}）：{t.weight}%（每 {PITY_THRESHOLD} 抽保底 SSR）" for t in TIERS]
    return "\n".join(lines)


async def get_pity_count(session: AsyncSession, user_id: int) -> int:
    """Number of draws since the user's last SSR (pity counter)."""
    result = await session.execute(
        select(func.count())
        .select_from(GachaDraw)
        .where(
            GachaDraw.user_id == user_id,
            GachaDraw.id > (
                select(func.coalesce(func.max(GachaDraw.id), 0))
                .where(GachaDraw.user_id == user_id, GachaDraw.rarity == "SSR")
                .scalar_subquery()
            ),
        )
    )
    return result.scalar_one() or 0


async def record_draw(
    session: AsyncSession,
    user_id: int,
    rarity: str,
    scene_key: str,
    *,
    job_id: str | None = None,
    pity_count: int = 0,
) -> GachaDraw:
    draw = GachaDraw(
        user_id=user_id,
        rarity=rarity,
        scene_key=scene_key,
        job_id=job_id,
        cost_credits=GACHA_COST_CREDITS,
        pity_count=pity_count,
        drawn_at=datetime.now(timezone.utc),
    )
    session.add(draw)
    await session.flush()
    return draw


async def execute_gacha_draw(
    session: AsyncSession,
    user_id: int,
    *,
    nsfw: bool = False,
    persona_slug: str | None = None,
) -> GachaDraw:
    """
    Debit credits, roll rarity (with pity), pick scene, enqueue image job.
    Raises InsufficientCreditsError if wallet is too low.
    """
    from shared.wallet import WalletService

    # Debit credits first (raises InsufficientCreditsError if not enough).
    await WalletService(session).debit(
        user_id,
        GACHA_COST_CREDITS,
        reason="gacha_draw",
    )

    pity = await get_pity_count(session, user_id)
    force_ssr = pity >= PITY_THRESHOLD
    rarity = sample_rarity(force_ssr=force_ssr)
    scene_key = sample_scene(rarity, nsfw=nsfw)

    # Downgrade SSR scene if NSFW not allowed.
    if not nsfw and rarity == "SSR":
        rarity = "SR"
        scene_key = sample_scene(rarity, nsfw=nsfw)

    # Enqueue photo job.
    job_id = await request_photo(
        user_id,
        nsfw=nsfw,
        scene=scene_key,
        persona_slug=persona_slug,
    )

    return await record_draw(
        session,
        user_id,
        rarity,
        scene_key,
        job_id=job_id,
        pity_count=pity,
    )
