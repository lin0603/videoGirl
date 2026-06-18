"""Tests for natural-language reminders."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from shared.models import Reminder
from shared.reminders import ReminderService
from shared.repositories.user_repo import UserRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _create_user(session, telegram_id: int = 500):
    return await UserRepository(session).create_or_update(
        telegram_id=telegram_id,
        username="tester",
        display_name="Tester",
    )


def _mock_llm_json(content: str, due_at: str, recurrence: str = "once", reminder_type: str = "custom"):
    payload = (
        '{"content": "%s", "due_at": "%s", "recurrence": "%s", "reminder_type": "%s"}'
        % (content, due_at, recurrence, reminder_type)
    )
    return AsyncMock(return_value=payload)


@pytest.mark.asyncio
async def test_create_reminder_from_text(db_session):
    user = await _create_user(db_session)
    user.timezone = "Asia/Taipei"
    await db_session.commit()

    service = ReminderService(db_session)
    with patch(
        "shared.reminders.get_llm_client",
        return_value=MagicMock(
            chat=_mock_llm_json("繳電費", "2026-06-20T15:00:00", "once", "bill")
        ),
    ):
        parsed = await service.parse_and_create(
            user.telegram_id,
            "明天下午三點繳電費",
            timezone_str=user.timezone,
        )
    assert parsed.content == "繳電費"
    assert parsed.recurrence == "once"
    assert parsed.due_at >= _utc_now()


@pytest.mark.asyncio
async def test_get_due_reminders_and_reschedule(db_session):
    user = await _create_user(db_session)
    service = ReminderService(db_session)

    reminder = Reminder(
        user_id=user.telegram_id,
        content="繳稅",
        reminder_type="tax",
        recurrence="monthly",
        due_at=_utc_now() - timedelta(minutes=1),
        timezone="Asia/Taipei",
        status="active",
    )
    db_session.add(reminder)
    await db_session.commit()

    due = await service.get_due_reminders()
    assert any(r.id == reminder.id for r in due)

    await service.mark_delivered_and_reschedule(reminder)
    assert reminder.status == "active"  # monthly stays active
    assert reminder.due_at > _utc_now()


@pytest.mark.asyncio
async def test_recurring_monthly_next_occurrence(db_session):
    user = await _create_user(db_session)
    service = ReminderService(db_session)

    due = datetime(2026, 1, 31, 9, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    reminder = Reminder(
        user_id=user.telegram_id,
        content="月底繳費",
        recurrence="monthly",
        due_at=due.astimezone(timezone.utc),
        timezone="Asia/Taipei",
    )
    db_session.add(reminder)
    await db_session.commit()

    next_due = service._next_occurrence(reminder)
    local = next_due.astimezone(ZoneInfo("Asia/Taipei"))
    assert local.month == 2
    assert local.day in (28, 29)


@pytest.mark.asyncio
async def test_cancel_reminder(db_session):
    user = await _create_user(db_session)
    service = ReminderService(db_session)

    with patch(
        "shared.reminders.get_llm_client",
        return_value=MagicMock(
            chat=_mock_llm_json("倒垃圾", "2026-06-21T09:00:00")
        ),
    ):
        await service.parse_and_create(user.telegram_id, "後天倒垃圾", timezone_str="Asia/Taipei")

    reminders = await service.list_active(user.telegram_id)
    reminder_id = reminders[0].id
    cancelled = await service.cancel(reminder_id, user.telegram_id)
    assert cancelled.status == "cancelled"
    assert not await service.list_active(user.telegram_id)


@pytest.mark.asyncio
async def test_one_time_reminder_marked_done(db_session):
    user = await _create_user(db_session)
    service = ReminderService(db_session)

    reminder = Reminder(
        user_id=user.telegram_id,
        content="打疫苗",
        recurrence="once",
        due_at=_utc_now() - timedelta(minutes=5),
        timezone="Asia/Taipei",
        status="active",
    )
    db_session.add(reminder)
    await db_session.commit()

    await service.mark_delivered_and_reschedule(reminder)
    assert reminder.status == "done"
