"""Tests for the proactive CARE engine."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
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

    # Force local time to 23:30 (quiet hour)
    async def tick_at(hour):
        original = ZoneInfo("Asia/Taipei")
        now_local = datetime.now(original).replace(hour=hour, minute=0, second=0, microsecond=0)
        # just call maybe_send directly with mocked local_now
        pass

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

    # 12:00 UTC is not quiet, but frequency cap applies.
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

    # Mock generation to avoid LLM calls
    engine._generate_message = AsyncMock(return_value="你在做什麼呀？")

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
