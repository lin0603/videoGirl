"""Tests for the companion mood model."""

from datetime import datetime, timedelta, timezone

import pytest

from shared.mood import MoodService, format_mood_for_prompt
from shared.repositories.mood_repo import MoodRepository
from shared.repositories.user_repo import UserRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _create_test_user(session, telegram_id: int = 100):
    return await UserRepository(session).create_or_update(
        telegram_id=telegram_id,
        username="tester",
        display_name="Tester",
    )


@pytest.mark.asyncio
async def test_chat_event_increases_affection(db_session):
    user = await _create_test_user(db_session)
    service = MoodService(db_session)

    snapshot = await service.process_event(user.telegram_id, "xiaorou", "chat")
    assert snapshot.affection > 0
    assert snapshot.upset < 0


@pytest.mark.asyncio
async def test_gift_event_boosts_affection_and_clears_upset(db_session):
    user = await _create_test_user(db_session)
    service = MoodService(db_session)

    await service.process_event(user.telegram_id, "xiaorou", "ignored")
    before = await service.get_mood(user.telegram_id, "xiaorou")
    assert before.upset > 0

    after = await service.process_event(user.telegram_id, "xiaorou", "gift")
    assert after.affection > before.affection
    assert after.upset < before.upset


@pytest.mark.asyncio
async def test_silence_event_increases_longing(db_session):
    user = await _create_test_user(db_session)
    service = MoodService(db_session)

    snapshot = await service.process_event(user.telegram_id, "xiaorou", "silence")
    assert snapshot.longing > 0


@pytest.mark.asyncio
async def test_mood_decay_returns_to_baseline(db_session):
    user = await _create_test_user(db_session)
    service = MoodService(db_session)

    await service.process_event(user.telegram_id, "xiaorou", "gift")
    mood = await MoodRepository(db_session).get(user.telegram_id, "xiaorou")
    # Simulate a long silence
    mood.last_interaction_at = _utc_now() - timedelta(days=7)
    await db_session.commit()

    snapshot = await service.get_mood(user.telegram_id, "xiaorou")
    assert abs(snapshot.affection) < 0.3
    assert abs(snapshot.longing) < 0.3


@pytest.mark.asyncio
async def test_chat_message_detects_warm_text(db_session):
    user = await _create_test_user(db_session)
    service = MoodService(db_session)

    phrase = await service.process_chat_message(
        user.telegram_id, "xiaorou", "早安，我愛妳"
    )
    mood = await service.get_mood(user.telegram_id, "xiaorou")
    assert mood.affection > 0.08
    assert "此刻心情" in format_mood_for_prompt(phrase)


@pytest.mark.asyncio
async def test_chat_message_detects_silence(db_session):
    user = await _create_test_user(db_session)
    service = MoodService(db_session)

    # First interaction
    await service.process_event(user.telegram_id, "xiaorou", "chat")
    mood = await MoodRepository(db_session).get(user.telegram_id, "xiaorou")
    mood.last_interaction_at = _utc_now() - timedelta(hours=5)
    await db_session.commit()

    phrase = await service.process_chat_message(user.telegram_id, "xiaorou", "hi")
    assert "想" in phrase or "寂寞" in phrase or "陪" in phrase
