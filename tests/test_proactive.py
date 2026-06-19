"""Tests for the proactive CARE engine."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from shared.models import CompanionMood, User
from shared.proactive import DEFAULT_TZ, ProactiveEngine, _choose_prompt, _is_quiet_hour
from shared.repositories.mood_repo import MoodRepository
from shared.repositories.user_repo import UserRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_quiet_hour_blocks_message(db_session):
    user = await UserRepository(db_session).create_or_update(
        telegram_id=400, username="tester", display_name="Tester"
    )
    user.age_verified_at = _utc_now()
    user.timezone = "Asia/Taipei"
    await db_session.commit()

    mood = await MoodRepository(db_session).get_or_create(user.telegram_id, "xiaorou")
    mood.last_interaction_at = _utc_now() - timedelta(hours=5)
    await db_session.commit()

    bot = MagicMock()
    bot.send_message = AsyncMock()
    engine = ProactiveEngine(bot, session_factory=lambda: db_session)
    engine._generate_message = AsyncMock(return_value="test")

    # Force local time to 23:30 (quiet hour)
    quiet_local = datetime(2026, 1, 1, 23, 30, tzinfo=ZoneInfo("Asia/Taipei"))
    with patch("shared.proactive._local_now", return_value=quiet_local):
        sent = await engine._maybe_send_to_user(db_session, user)
    assert sent is False
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_frequency_cap_blocks_message(db_session):
    user = await UserRepository(db_session).create_or_update(
        telegram_id=401, username="tester", display_name="Tester"
    )
    user.age_verified_at = _utc_now()
    user.timezone = "Etc/UTC"
    await db_session.commit()

    mood = await MoodRepository(db_session).get_or_create(user.telegram_id, "xiaorou")
    mood.last_interaction_at = _utc_now() - timedelta(hours=5)
    mood.last_proactive_at = _utc_now() - timedelta(minutes=10)
    await db_session.commit()

    bot = MagicMock()
    bot.send_message = AsyncMock()
    engine = ProactiveEngine(bot, session_factory=lambda: db_session)
    engine._generate_message = AsyncMock(return_value="test")

    # 12:00 UTC is not quiet, but frequency cap applies.
    noon_local = datetime(2026, 1, 1, 12, 0, tzinfo=ZoneInfo("Etc/UTC"))
    with patch("shared.proactive._local_now", return_value=noon_local):
        sent = await engine._maybe_send_to_user(db_session, user)
    assert sent is False
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_care_prompt_selected_after_silence(db_session):
    user = await UserRepository(db_session).create_or_update(
        telegram_id=402, username="tester", display_name="Tester"
    )
    user.age_verified_at = _utc_now()
    user.timezone = "Etc/UTC"
    await db_session.commit()

    mood = await MoodRepository(db_session).get_or_create(user.telegram_id, "xiaorou")
    mood.last_interaction_at = _utc_now() - timedelta(hours=5)
    await db_session.commit()

    bot = MagicMock()
    bot.send_message = AsyncMock()
    engine = ProactiveEngine(bot, session_factory=lambda: db_session)
    engine._generate_message = AsyncMock(return_value="你在做什麼呀？")

    # 15:00 UTC falls in the care-check window and there has been 5h of silence.
    afternoon_local = datetime(2026, 1, 1, 15, 0, tzinfo=ZoneInfo("Etc/UTC"))
    with patch("shared.proactive._local_now", return_value=afternoon_local):
        sent = await engine._maybe_send_to_user(db_session, user)
    assert sent is True
    bot.send_message.assert_awaited_once()

    refreshed = await MoodRepository(db_session).get(user.telegram_id, "xiaorou")
    assert refreshed.last_proactive_at is not None


@pytest.mark.asyncio
async def test_morning_prompt_selected(db_session):
    user = await UserRepository(db_session).create_or_update(
        telegram_id=403, username="tester", display_name="Tester"
    )
    user.age_verified_at = _utc_now()
    user.timezone = "Etc/UTC"
    await db_session.commit()

    mood = await MoodRepository(db_session).get_or_create(user.telegram_id, "xiaorou")
    mood.last_interaction_at = _utc_now() - timedelta(hours=10)
    await db_session.commit()

    bot = MagicMock()
    bot.send_message = AsyncMock()
    engine = ProactiveEngine(bot, session_factory=lambda: db_session)
    engine._generate_message = AsyncMock(return_value="早安～")

    # Manually choose prompt at 9 AM local
    prompt = _choose_prompt(datetime(2026, 1, 1, 9, 0, tzinfo=ZoneInfo("Etc/UTC")), mood.last_interaction_at)
    assert prompt is not None
    assert prompt.label == "早安"


@pytest.mark.asyncio
async def test_opt_out_user_not_selected(db_session):
    user = await UserRepository(db_session).create_or_update(
        telegram_id=404, username="tester", display_name="Tester"
    )
    user.age_verified_at = _utc_now()
    user.proactive_opt_out = True
    await db_session.commit()

    eligible = await UserRepository(db_session).list_proactive_eligible()
    assert all(u.telegram_id != user.telegram_id for u in eligible)
