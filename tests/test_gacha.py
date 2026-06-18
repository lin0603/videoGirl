"""Tests for task #25: gacha photo pack."""
from unittest.mock import AsyncMock, patch

from shared.repositories.user_repo import UserRepository
from shared.wallet import WalletService


async def _make_user(session, uid: int):
    return await UserRepository(session).create_or_update(
        telegram_id=uid, username="gachatest", display_name="GachaTest"
    )


# ---- rarity sampling ----

def test_sample_rarity_returns_valid_tier() -> None:
    from shared.gacha import sample_rarity, TIERS
    for _ in range(20):
        r = sample_rarity()
        assert r in {t.key for t in TIERS}


def test_sample_rarity_force_ssr() -> None:
    from shared.gacha import sample_rarity
    for _ in range(10):
        assert sample_rarity(force_ssr=True) == "SSR"


def test_sample_scene_sfw_excludes_nsfw() -> None:
    from shared.gacha import sample_scene
    for _ in range(20):
        scene = sample_scene("SSR", nsfw=False)
        assert scene not in ("topless", "nsfw_full")


def test_sample_scene_nsfw_can_return_nsfw() -> None:
    from shared.gacha import sample_scene
    # SSR scenes with nsfw=True should include NSFW options.
    found_nsfw = False
    for _ in range(50):
        scene = sample_scene("SSR", nsfw=True)
        if scene in ("topless", "nsfw_full"):
            found_nsfw = True
            break
    assert found_nsfw


# ---- pity counter ----

async def test_pity_count_zero_initially(db_session) -> None:
    from shared.gacha import get_pity_count
    await _make_user(db_session, 6001)
    assert await get_pity_count(db_session, 6001) == 0


async def test_pity_count_increments_on_non_ssr(db_session) -> None:
    from shared.gacha import get_pity_count, record_draw
    await _make_user(db_session, 6002)
    await record_draw(db_session, 6002, "R", "selfie")
    await record_draw(db_session, 6002, "SR", "lingerie")
    assert await get_pity_count(db_session, 6002) == 2


async def test_pity_count_resets_after_ssr(db_session) -> None:
    from shared.gacha import get_pity_count, record_draw
    await _make_user(db_session, 6003)
    await record_draw(db_session, 6003, "R", "selfie")
    await record_draw(db_session, 6003, "SSR", "topless")
    await record_draw(db_session, 6003, "R", "portrait")
    # Only the last draw after SSR counts.
    assert await get_pity_count(db_session, 6003) == 1


# ---- execute_gacha_draw ----

async def test_gacha_draw_debits_credits(db_session) -> None:
    from shared.gacha import execute_gacha_draw, GACHA_COST_CREDITS
    user = await _make_user(db_session, 6004)
    await WalletService(db_session).top_up(6004, 50, reason="test")

    with patch("shared.gacha.request_photo", new=AsyncMock(return_value="job-g-001")):
        draw = await execute_gacha_draw(db_session, 6004, nsfw=False)

    balance = await WalletService(db_session).get_balance(6004)
    assert balance == 50 - GACHA_COST_CREDITS
    assert draw.rarity in ("R", "SR", "SSR")
    assert draw.job_id == "job-g-001"


async def test_gacha_draw_raises_on_insufficient_credits(db_session) -> None:
    from shared.gacha import execute_gacha_draw
    from shared.wallet import InsufficientCreditsError
    await _make_user(db_session, 6005)
    # No top-up → wallet is empty.
    import pytest
    with patch("shared.gacha.request_photo", new=AsyncMock(return_value=None)):
        with pytest.raises(InsufficientCreditsError):
            await execute_gacha_draw(db_session, 6005, nsfw=False)
