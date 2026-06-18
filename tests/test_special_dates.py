"""Tests for task #33: special dates + proactive gift messages."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from shared.special_dates import SpecialDateService


@pytest.fixture(autouse=True)
async def clean_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE special_dates, users RESTART IDENTITY CASCADE"))


async def _make_user(db_engine, telegram_id: int = 8001) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (telegram_id, nsfw_opt_in, locale, timezone, proactive_opt_out,"
                " voice_enabled, voice_slug, voice_speed) VALUES "
                "(:id, false, 'zh-TW', 'Asia/Taipei', false, false, 'default', 1.0)"
            ),
            {"id": telegram_id},
        )


async def test_upsert_birthday(db_session, db_engine) -> None:
    await _make_user(db_engine)
    svc = SpecialDateService(db_session)
    sd = await svc.upsert(
        user_id=8001, date_type="birthday", month=6, day=15,
        label="我的生日", recurrent=True
    )
    assert sd.id is not None
    assert sd.month == 6
    assert sd.day == 15
    assert sd.date_type == "birthday"


async def test_upsert_replaces_existing(db_session, db_engine) -> None:
    await _make_user(db_engine)
    svc = SpecialDateService(db_session)
    await svc.upsert(user_id=8001, date_type="birthday", month=1, day=1, label="舊", recurrent=True)
    updated = await svc.upsert(user_id=8001, date_type="birthday", month=6, day=15, label="新", recurrent=True)
    assert updated.month == 6
    assert updated.label == "新"
    all_rows = await svc.list_for_user(8001)
    assert len(all_rows) == 1  # still one birthday


async def test_get_due_today_matches(db_session, db_engine) -> None:
    await _make_user(db_engine)
    svc = SpecialDateService(db_session)
    now = datetime.now(timezone.utc)
    await svc.upsert(
        user_id=8001, date_type="birthday",
        month=now.month, day=now.day, label="今天生日", recurrent=True,
    )
    due = await svc.get_due_today()
    assert any(sd.user_id == 8001 for sd in due)


async def test_get_due_today_excludes_already_greeted(db_session, db_engine) -> None:
    await _make_user(db_engine)
    svc = SpecialDateService(db_session)
    now = datetime.now(timezone.utc)
    sd = await svc.upsert(
        user_id=8001, date_type="birthday",
        month=now.month, day=now.day, label="今天生日", recurrent=True,
    )
    await svc.mark_greeted(sd)
    due = await svc.get_due_today()
    assert not any(s.user_id == 8001 for s in due)


async def test_get_due_today_no_match(db_session, db_engine) -> None:
    await _make_user(db_engine)
    svc = SpecialDateService(db_session)
    await svc.upsert(
        user_id=8001, date_type="birthday",
        month=1, day=1, label="元旦生日", recurrent=True,
    )
    now = datetime.now(timezone.utc)
    if now.month == 1 and now.day == 1:
        pytest.skip("Test happens to run on Jan 1")
    due = await svc.get_due_today()
    assert not any(s.user_id == 8001 for s in due)


async def test_mark_greeted_non_recurrent_deletes(db_session, db_engine) -> None:
    await _make_user(db_engine)
    svc = SpecialDateService(db_session)
    now = datetime.now(timezone.utc)
    sd = await svc.upsert(
        user_id=8001, date_type="custom",
        month=now.month, day=now.day, label="一次性", recurrent=False,
    )
    await svc.mark_greeted(sd)
    remaining = await svc.list_for_user(8001)
    assert len(remaining) == 0
