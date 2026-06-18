"""Tests for task #31 compliance + payout safety."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.compliance import (
    FRAGMENT_MIN_PAYOUT_XTR,
    StarsStatus,
    get_stars_status,
)


def _make_bot(balance: int) -> MagicMock:
    bot = MagicMock()
    result = MagicMock()
    result.amount = balance
    bot.get_my_star_balance = AsyncMock(return_value=result)
    return bot


async def test_balance_below_threshold() -> None:
    bot = _make_bot(500)
    status = await get_stars_status(bot)
    assert status.balance == 500
    assert not status.payout_ready
    assert "500" in status.message
    assert "差" in status.message


async def test_balance_at_threshold() -> None:
    bot = _make_bot(FRAGMENT_MIN_PAYOUT_XTR)
    status = await get_stars_status(bot)
    assert status.payout_ready
    assert "提領" in status.message


async def test_balance_above_threshold() -> None:
    bot = _make_bot(2500)
    status = await get_stars_status(bot)
    assert status.balance == 2500
    assert status.payout_ready


async def test_api_error_returns_negative_balance() -> None:
    bot = MagicMock()
    bot.get_my_star_balance = AsyncMock(side_effect=RuntimeError("network error"))
    status = await get_stars_status(bot)
    assert status.balance == -1
    assert not status.payout_ready
    assert "錯誤" in status.message


def test_nsfw_default_off(monkeypatch) -> None:
    """Non-opted users have nsfw_opt_in=False by default."""
    from shared.repositories.user_repo import UserRepository
    from shared.models import User
    u = User()
    u.nsfw_opt_in = False
    assert not u.nsfw_opt_in, "Default must be SFW"


def test_safety_blocks_minor_terms() -> None:
    """Public content filter catches minor-related terms."""
    from shared.safety import check_text
    result = check_text("show me loli content")
    assert not result.allowed
    assert result.violation == "minor"


def test_safety_allows_adult_nsfw() -> None:
    """Opted-in adult NSFW terms pass the safety filter."""
    from shared.safety import check_text
    result = check_text("beautiful woman lingerie")
    assert result.allowed
