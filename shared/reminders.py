"""Natural-language reminders engine (task #13).

Parses free-form Chinese reminders ("提醒我月底繳稅", "每月15號電費") into
structured reminders and delivers them in the girlfriend's voice.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.llm import LLMError, get_llm_client
from shared.logging import get_logger
from shared.models import Reminder

logger = get_logger("shared.reminders")

Recurrence = Literal["once", "daily", "weekly", "monthly", "yearly"]
ReminderType = Literal["bill", "tax", "chore", "custom"]


@dataclass
class ParsedReminder:
    content: str
    due_at: datetime
    recurrence: Recurrence
    reminder_type: ReminderType


PARSE_PROMPT = """你是一個繁體中文生活助理。請把使用者的提醒句子解析成 JSON。

輸入格式範例：
- "提醒我明天下午三點繳電費"
- "每月15號繳信用卡"
- "每週二倒垃圾"
- "2026/05/31 前要報稅"

現在時間（台灣時區 Asia/Taipei）：{now_tw}

請輸出嚴格 JSON，欄位如下：
{{
  "content": "提醒內容（簡潔、使用女友口吻會用到的內容，例如『繳電費』）",
  "due_at": "YYYY-MM-DDTHH:MM:SS",
  "recurrence": "once | daily | weekly | monthly | yearly",
  "reminder_type": "bill | tax | chore | custom"
}}

如果時間不明確，預設為當天早上 9 點。請只輸出 JSON，不要多餘文字。"""


class ReminderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def parse_and_create(
        self,
        user_id: int,
        text: str,
        timezone_str: str = "Asia/Taipei",
    ) -> ParsedReminder:
        """Parse natural-language text and create a Reminder row."""
        parsed = await self._parse(text, timezone_str)
        reminder = Reminder(
            user_id=user_id,
            content=parsed.content,
            reminder_type=parsed.reminder_type,
            recurrence=parsed.recurrence,
            due_at=parsed.due_at,
            timezone=timezone_str,
            status="active",
        )
        self.session.add(reminder)
        await self.session.commit()
        await self.session.refresh(reminder)
        logger.info(
            "reminder_created",
            user_id=user_id,
            reminder_id=reminder.id,
            content=reminder.content,
            due_at=reminder.due_at.isoformat(),
        )
        return parsed

    async def list_active(self, user_id: int, limit: int = 20) -> list[Reminder]:
        result = await self.session.execute(
            select(Reminder)
            .where(
                Reminder.user_id == user_id,
                Reminder.status == "active",
            )
            .order_by(Reminder.due_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def cancel(self, reminder_id: int, user_id: int) -> Reminder | None:
        result = await self.session.execute(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.user_id == user_id,
            )
        )
        reminder = result.scalar_one_or_none()
        if reminder is None:
            return None
        reminder.status = "cancelled"
        await self.session.commit()
        return reminder

    async def get_due_reminders(
        self, before: datetime | None = None
    ) -> list[Reminder]:
        """Return active reminders whose due_at has passed."""
        now = before or datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Reminder).where(
                Reminder.status == "active",
                Reminder.due_at <= now,
            )
        )
        return list(result.scalars().all())

    async def mark_delivered_and_reschedule(self, reminder: Reminder) -> None:
        """Mark a one-time reminder done or reschedule a recurring one."""
        now = datetime.now(timezone.utc)
        if reminder.recurrence == "once":
            reminder.status = "done"
        else:
            reminder.due_at = self._next_occurrence(reminder)
        reminder.updated_at = now
        await self.session.commit()

    @staticmethod
    def _next_occurrence(reminder: Reminder) -> datetime:
        tz = ZoneInfo(reminder.timezone)
        local = reminder.due_at.astimezone(tz)
        if reminder.recurrence == "daily":
            local = local + timedelta(days=1)
        elif reminder.recurrence == "weekly":
            local = local + timedelta(weeks=1)
        elif reminder.recurrence == "monthly":
            # Simple month increment; day clamp handled by replace fallback.
            month = local.month + 1
            year = local.year
            if month > 12:
                month = 1
                year += 1
            try:
                local = local.replace(year=year, month=month)
            except ValueError:
                local = local.replace(year=year, month=month, day=1) + timedelta(days=31)
                local = local.replace(day=1) - timedelta(days=1)
        elif reminder.recurrence == "yearly":
            try:
                local = local.replace(year=local.year + 1)
            except ValueError:
                local = local.replace(year=local.year + 1, day=28)
        return local.astimezone(timezone.utc)

    async def _parse(self, text: str, timezone_str: str) -> ParsedReminder:
        tz = ZoneInfo(timezone_str)
        now_tw = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
        messages = [
            {"role": "system", "content": PARSE_PROMPT.format(now_tw=now_tw)},
            {"role": "user", "content": text},
        ]
        try:
            raw = await get_llm_client().chat(messages, max_tokens=200)
        except LLMError as exc:
            logger.error("reminder_parse_llm_failed", error=str(exc))
            raise ReminderParseError("無法解析提醒時間，請換個說法試試看。") from exc

        parsed = self._extract_json(raw)
        due_at = self._normalize_due_at(parsed.get("due_at", ""), tz)
        recurrence = self._normalize_recurrence(parsed.get("recurrence", "once"))
        reminder_type = self._normalize_type(parsed.get("reminder_type", "custom"))
        content = parsed.get("content", text).strip() or text

        return ParsedReminder(
            content=content,
            due_at=due_at,
            recurrence=recurrence,
            reminder_type=reminder_type,
        )

    @staticmethod
    def _extract_json(raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("reminder_parse_json_failed", raw=raw)
            raise ReminderParseError("解析格式錯誤，請再說一次。") from exc

    @staticmethod
    def _normalize_due_at(value: str, tz: ZoneInfo) -> datetime:
        value = value.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value, fmt)
                if fmt == "%Y-%m-%d":
                    dt = dt.replace(hour=9, minute=0, second=0)
                return dt.replace(tzinfo=tz).astimezone(timezone.utc)
            except ValueError:
                continue
        # Fallback: tomorrow 09:00 local
        tomorrow = datetime.now(tz) + timedelta(days=1)
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    @staticmethod
    def _normalize_recurrence(value: str) -> Recurrence:
        value = (value or "once").lower().strip()
        if value in ("once", "daily", "weekly", "monthly", "yearly"):
            return value  # type: ignore[return-value]
        return "once"

    @staticmethod
    def _normalize_type(value: str) -> ReminderType:
        value = (value or "custom").lower().strip()
        if value in ("bill", "tax", "chore", "custom"):
            return value  # type: ignore[return-value]
        return "custom"


class ReminderParseError(ValueError):
    pass
