"""Tests for task #24: gamified intimacy system."""
from datetime import datetime, timedelta, timezone

from shared.repositories.user_repo import UserRepository


async def _make_user(session, uid: int):
    return await UserRepository(session).create_or_update(
        telegram_id=uid, username="intimacytest", display_name="IntimacyTest"
    )


def test_level_thresholds_ascending() -> None:
    from shared.intimacy import LEVEL_THRESHOLDS
    assert LEVEL_THRESHOLDS == sorted(LEVEL_THRESHOLDS)
    assert LEVEL_THRESHOLDS[0] == 0


async def test_initial_status_is_zero(db_session) -> None:
    from shared.intimacy import IntimacyService
    await _make_user(db_session, 7001)
    status = await IntimacyService(db_session).get_status(7001)
    assert status.level == 0
    assert status.score == 0.0
    assert status.streak == 0


async def test_interaction_increases_score(db_session) -> None:
    from shared.intimacy import IntimacyService, CHAT_SCORE_DELTA
    await _make_user(db_session, 7002)
    svc = IntimacyService(db_session)
    rel = await svc.record_interaction(7002)
    assert rel.affection_score >= CHAT_SCORE_DELTA


async def test_consecutive_day_streak(db_session) -> None:
    from shared.intimacy import IntimacyService, STREAK_BONUS
    from unittest.mock import patch
    await _make_user(db_session, 7003)
    svc = IntimacyService(db_session)

    day1 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)

    with patch("shared.intimacy.datetime") as mock_dt:
        mock_dt.now.return_value = day1
        mock_dt.now.side_effect = None
        await svc.record_interaction(7003)

    with patch("shared.intimacy.datetime") as mock_dt:
        mock_dt.now.return_value = day2
        mock_dt.now.side_effect = None
        rel = await svc.record_interaction(7003)

    # Second interaction on next day should increase streak.
    assert rel.streak_days >= 1


async def test_gift_adds_more_score_than_chat(db_session) -> None:
    from shared.intimacy import IntimacyService, CHAT_SCORE_DELTA, GIFT_SCORE_DELTA
    await _make_user(db_session, 7004)
    svc = IntimacyService(db_session)

    rel_chat = await svc.record_interaction(7004, delta=CHAT_SCORE_DELTA)
    before_gift = rel_chat.affection_score
    rel_gift = await svc.record_gift(7004)
    added = rel_gift.affection_score - before_gift
    assert added >= GIFT_SCORE_DELTA


async def test_level_increases_at_threshold(db_session) -> None:
    from shared.intimacy import IntimacyService, LEVEL_THRESHOLDS
    await _make_user(db_session, 7005)
    svc = IntimacyService(db_session)
    # Push score past first level threshold.
    threshold = LEVEL_THRESHOLDS[1]
    await svc.record_interaction(7005, delta=float(threshold + 1))
    status = await svc.get_status(7005)
    assert status.level >= 1


async def test_intimacy_level_convenience(db_session) -> None:
    from shared.intimacy import IntimacyService
    await _make_user(db_session, 7006)
    svc = IntimacyService(db_session)
    assert await svc.intimacy_level(7006) == 0
