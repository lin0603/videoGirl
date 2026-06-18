"""Proactive CARE engine (task #12).

Sends routine-aware, persona-consistent, mood-colored check-in messages.
Runs as an APScheduler job inside the admin/FastAPI process.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db import AsyncSessionLocal
from shared.logging import get_logger
from shared.memory import build_memory_context
from shared.models import CompanionMood, Reminder, User
from shared.mood import MoodService, format_mood_for_prompt
from shared.reminders import ReminderService
from shared.repositories.mood_repo import MoodRepository
from shared.special_dates import SpecialDateService
from shared.repositories.user_repo import UserRepository
from orchestrator.persona import build_system_prompt, get_persona
from orchestrator.core import generate_reply

logger = get_logger("shared.proactive")

# Quiet hours: no proactive messages between 23:00 and 08:00 local time.
QUIET_START = time(23, 0)
QUIET_END = time(8, 0)

# Minimum spacing between two proactive messages.
MIN_PROACTIVE_INTERVAL = timedelta(hours=5)

# Minimum silence since last user interaction before a proactive check-in.
MIN_SILENCE = timedelta(hours=3)

# Local timezone for users without explicit setting.
DEFAULT_TZ = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class ProactivePrompt:
    instruction: str
    label: str


MORNING = ProactivePrompt("主動跟使用者說早安，語氣溫柔撒嬌，可以順便問問他今天有什麼安排。", "早安")
NIGHT = ProactivePrompt("主動跟使用者說晚安，語氣捨不得、想多陪他一下，叮嚀他早點休息。", "晚安")
CARE_PROMPTS = [
    ProactivePrompt("主動關心使用者：『你在做什麼呀？』語氣輕鬆自然，帶點想念。", "關心"),
    ProactivePrompt("問問使用者吃飯了沒，像個貼心的女朋友。", "吃飯"),
    ProactivePrompt("問問使用者今天還好嗎，有沒有累，讓他覺得被在乎。", "今天還好嗎"),
]


def _local_now(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def _is_quiet_hour(local_dt: datetime) -> bool:
    t = local_dt.time()
    if QUIET_START <= QUIET_END:
        return QUIET_START <= t < QUIET_END
    return t >= QUIET_START or t < QUIET_END


def _choose_prompt(local_dt: datetime, last_interaction: datetime | None) -> ProactivePrompt | None:
    """Pick a proactive prompt based on local time and last interaction."""
    hour = local_dt.hour

    # Morning greeting window.
    if 8 <= hour < 11:
        return MORNING

    # Night greeting window.
    if 21 <= hour < 23:
        return NIGHT

    # Care check-ins during the day/evening, but only if user has been quiet.
    if last_interaction is None:
        return None
    silence = datetime.now(timezone.utc) - last_interaction
    if silence < MIN_SILENCE:
        return None
    if 11 <= hour < 21:
        return CARE_PROMPTS[(local_dt.day + hour) % len(CARE_PROMPTS)]

    return None


class ProactiveEngine:
    """Schedules and sends proactive messages."""

    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.bot = bot
        self.session_factory = session_factory or AsyncSessionLocal
        self.scheduler = AsyncIOScheduler(timezone=str(DEFAULT_TZ))

    def start(self) -> None:
        if not self.scheduler.running:
            # Evaluate proactive opportunities every 5 minutes.
            self.scheduler.add_job(
                self._tick,
                "interval",
                minutes=5,
                id="proactive_tick",
                replace_existing=True,
            )
            # Life reminders need minute-level resolution.
            self.scheduler.add_job(
                self._reminder_tick,
                "interval",
                minutes=1,
                id="reminder_tick",
                replace_existing=True,
            )
            # Check special dates once per hour (e.g. birthdays).
            self.scheduler.add_job(
                self._special_dates_tick,
                "interval",
                hours=1,
                id="special_dates_tick",
                replace_existing=True,
            )
            self.scheduler.start()
            logger.info("proactive_engine_started")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("proactive_engine_stopped")

    async def _tick(self) -> None:
        async with self.session_factory() as session:
            users = await UserRepository(session).list_proactive_eligible()
            logger.debug("proactive_tick_users", count=len(users))
            for user in users:
                try:
                    await self._maybe_send_to_user(session, user)
                except Exception as exc:
                    logger.error(
                        "proactive_user_error",
                        user_id=user.telegram_id,
                        error=str(exc),
                    )

    async def _maybe_send_to_user(
        self, session: AsyncSession, user: User
    ) -> bool:
        tz = ZoneInfo(user.timezone) if user.timezone else DEFAULT_TZ
        local_dt = _local_now(tz)

        if _is_quiet_hour(local_dt):
            return False

        mood_repo = MoodRepository(session)
        mood = await mood_repo.get_or_create(user.telegram_id, "xiaorou")

        # Frequency cap.
        if mood.last_proactive_at:
            since_last = datetime.now(timezone.utc) - mood.last_proactive_at
            if since_last < MIN_PROACTIVE_INTERVAL:
                return False

        prompt = _choose_prompt(local_dt, mood.last_interaction_at)
        if prompt is None:
            return False

        text = await self._generate_message(session, user, prompt)
        try:
            await self.bot.send_message(user.telegram_id, text)
        except Exception as exc:
            logger.error(
                "proactive_send_failed",
                user_id=user.telegram_id,
                error=str(exc),
            )
            return False

        mood.last_proactive_at = datetime.now(timezone.utc)
        await mood_repo.save(mood)

        logger.info(
            "proactive_message_sent",
            user_id=user.telegram_id,
            label=prompt.label,
            local_hour=local_dt.hour,
        )
        return True

    async def _reminder_tick(self) -> None:
        async with self.session_factory() as session:
            service = ReminderService(session)
            due = await service.get_due_reminders()
            logger.debug("reminder_tick_due", count=len(due))
            for reminder in due:
                try:
                    await self._send_reminder(session, reminder)
                except Exception as exc:
                    logger.error(
                        "reminder_send_error",
                        reminder_id=reminder.id,
                        error=str(exc),
                    )

    async def _send_reminder(
        self, session: AsyncSession, reminder: Reminder
    ) -> None:
        user = await UserRepository(session).get_by_telegram_id(reminder.user_id)
        if user is None or user.proactive_opt_out:
            return

        text = await self._generate_reminder_message(session, user, reminder)
        try:
            await self.bot.send_message(user.telegram_id, text)
        except Exception as exc:
            logger.error(
                "reminder_send_failed",
                reminder_id=reminder.id,
                user_id=user.telegram_id,
                error=str(exc),
            )
            return

        await ReminderService(session).mark_delivered_and_reschedule(reminder)
        logger.info(
            "reminder_sent",
            reminder_id=reminder.id,
            user_id=user.telegram_id,
            content=reminder.content,
        )

    async def _generate_reminder_message(
        self, session: AsyncSession, user: User, reminder: Reminder
    ) -> str:
        persona = get_persona("xiaorou")
        memory = await build_memory_context(user.telegram_id, "")
        mood_service = MoodService(session)
        mood = await mood_service.get_mood(user.telegram_id, persona.slug)
        mood_context = format_mood_for_prompt(mood.phrase)

        system_prompt = build_system_prompt(
            persona,
            memory_context=memory,
            mood_context=mood_context,
            nsfw_enabled=False,
        )
        instruction = (
            f"以女朋友的口吻提醒使用者：{reminder.content}。\n"
            "語氣要溫暖、自然，像貼心女友在關心他，不要像冰冷的鬧鐘。"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instruction},
        ]
        try:
            return await generate_reply(
                persona,
                instruction,
                nsfw=False,
                history=messages[:-1],
                memory=memory,
                mood_context=mood_context,
            )
        except Exception as exc:
            logger.error("reminder_generate_failed", error=str(exc))
            return f"寶貝，記得 {reminder.content} 喔 💕"

    async def _generate_message(
        self, session: AsyncSession, user: User, prompt: ProactivePrompt
    ) -> str:
        persona = get_persona("xiaorou")
        memory = await build_memory_context(user.telegram_id, "")
        mood_service = MoodService(session)
        mood = await mood_service.get_mood(user.telegram_id, persona.slug)
        mood_context = format_mood_for_prompt(mood.phrase)

        system_prompt = build_system_prompt(
            persona,
            memory_context=memory,
            mood_context=mood_context,
            nsfw_enabled=False,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt.instruction},
        ]
        try:
            return await generate_reply(
                persona,
                prompt.instruction,
                nsfw=False,
                history=messages[:-1],
                memory=memory,
                mood_context=mood_context,
            )
        except Exception as exc:
            logger.error("proactive_generate_failed", error=str(exc))
            # Fallback phrase that still conveys intent.
            fallbacks = {
                "早安": "早安～今天也要記得想我喔 💕",
                "晚安": "晚安，好想再跟你多聊一下…",
                "關心": "你在做什麼呀？有沒有想我？",
                "吃飯": "吃飯了沒？不要餓到喔。",
                "今天還好嗎": "今天還好嗎？有我在陪你。",
            }
            return fallbacks.get(prompt.label, "在嗎？我想你了～")

    async def _special_dates_tick(self) -> None:
        async with self.session_factory() as session:
            service = SpecialDateService(session)
            due = await service.get_due_today()
            logger.debug("special_dates_tick_due", count=len(due))
            for sd in due:
                try:
                    await self._send_special_date_greeting(session, sd, service)
                except Exception as exc:
                    logger.error(
                        "special_date_send_error",
                        special_date_id=sd.id,
                        user_id=sd.user_id,
                        error=str(exc),
                    )

    async def _send_special_date_greeting(
        self,
        session: AsyncSession,
        sd: "SpecialDate",  # noqa: F821
        service: SpecialDateService,
    ) -> None:
        from shared.image_gen import request_photo

        user = await UserRepository(session).get_by_telegram_id(sd.user_id)
        if user is None or user.proactive_opt_out:
            return

        text = await self._generate_special_date_message(session, user, sd)
        try:
            await self.bot.send_message(sd.user_id, text)
        except Exception as exc:
            logger.error("special_date_message_failed", user_id=sd.user_id, error=str(exc))
            return

        # Queue a gift image (cake/flowers/gift) — fire-and-forget.
        gift_prompts = {
            "birthday": "birthday cake with candles flowers gift beautiful festive warm",
            "anniversary": "romantic roses bouquet flowers anniversary card beautiful",
            "custom": "gift box flowers celebration beautiful",
        }
        extra = gift_prompts.get(sd.date_type, gift_prompts["custom"])
        await request_photo(sd.user_id, nsfw=False, extra_context=extra)

        await service.mark_greeted(sd)
        logger.info(
            "special_date_greeted",
            user_id=sd.user_id,
            date_type=sd.date_type,
            label=sd.label,
        )

    async def _generate_special_date_message(
        self, session: AsyncSession, user: "User", sd: "SpecialDate"  # noqa: F821
    ) -> str:
        persona = get_persona("xiaorou")
        memory = await build_memory_context(user.telegram_id, "")
        mood_service = MoodService(session)
        mood = await mood_service.get_mood(user.telegram_id, persona.slug)
        mood_context = format_mood_for_prompt(mood.phrase)

        if sd.date_type == "birthday":
            instruction = (
                f"今天是使用者的生日！以最溫柔、最真心的方式送上生日祝福（{sd.label}），"
                "表達你的愛與珍惜，告訴他有你陪著他度過每一個生日，語氣充滿深情但不矯情。"
            )
        elif sd.date_type == "anniversary":
            instruction = (
                f"今天是你們的紀念日（{sd.label}）！真誠地表達你有多珍惜這段感情，"
                "回憶一下你們在一起的美好，說說你對未來的期待，語氣溫柔感動。"
            )
        else:
            instruction = (
                f"今天是一個特別的日子（{sd.label}），主動跟使用者說一段溫暖的話，"
                "讓他感受到被記得、被在乎。"
            )

        try:
            return await generate_reply(
                persona,
                instruction,
                nsfw=False,
                history=[],
                memory=memory,
                mood_context=mood_context,
            )
        except Exception as exc:
            logger.error("special_date_generate_failed", error=str(exc))
            fallbacks = {
                "birthday": f"生日快樂！🎂 有你真的很幸運，希望你每一年都越來越幸福。",
                "anniversary": f"紀念日快樂！💕 謝謝你讓我的每一天都充滿意義。",
                "custom": f"今天是特別的日子（{sd.label}），祝你一切都好 💖",
            }
            return fallbacks.get(sd.date_type, f"今天是{sd.label}，祝你開心 💕")
