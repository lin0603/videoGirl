from zoneinfo import ZoneInfo

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.onboarding import start_onboarding
from bot.states import OnboardingState
from shared.logging import get_logger
from shared.mood import MoodService
from shared.referral import parse_start_payload, record_referral
from shared.reminders import ReminderParseError, ReminderService
from shared.repositories.user_repo import UserRepository
from shared.repositories.voice_repo import VoiceRepository

logger = get_logger("bot.commands")


def get_router() -> Router:
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
        # Parse deep-link payload (e.g. /start ref123456789)
        parts = (message.text or "").split(maxsplit=1)
        payload_str = parts[1].strip() if len(parts) > 1 else ""
        if payload_str:
            payload = parse_start_payload(payload_str)
            # Record attribution before onboarding (user might be new)
            await record_referral(
                session,
                referrer_id=payload.referrer_id,
                referred_id=message.from_user.id,
                source=payload.source,
            )

        await state.set_state(OnboardingState.age_gate)
        await start_onboarding(message, state, session)

    @router.message(Command("help"))
    async def cmd_help(message: types.Message) -> None:
        await message.answer(
            "可用指令：\n"
            "/start - 開始使用或重新進入驗證流程\n"
            "/help - 顯示說明\n"
            "/settings - 查看目前設定\n"
            "/toggle_nsfw - 切換 NSFW 開關\n"
            "/voice_on - 開啟語音回覆\n"
            "/voice_off - 關閉語音回覆\n"
            "/voice_settings - 查看語音設定\n"
            "/voice_list - 列出可選的語音類別\n"
            "/mood - 查看女友此刻心情\n"
            "/snooze - 暫停主動關心訊息\n"
            "/birthday MM-DD - 設定你的生日\n"
            "/anniversary MM-DD [說明] - 設定紀念日\n"
            "/remind <自然語言> - 新增生活提醒\n"
            "/reminders - 列出進行中的提醒\n"
            "/cancel_reminder <編號> - 取消提醒\n"
            "/voice_set <類別> - 選擇語音類別\n"
            "/personas - 查看可選的女友人設\n"
            "/switch <代碼> - 切換女友人設\n"
            "/products - 查看 Stars 數位商品\n"
            "/buy <商品代碼> - 開立 Telegram Stars 發票\n"
            "/subscribe - 訂閱 VIP 月方案\n"
            "/vip_status - 查看 VIP 狀態\n"
            "/cancel_vip - 取消 VIP 自動續訂\n"
            "/wallet - 查看點數餘額\n"
            "/topup - 用 Stars 儲值點數\n"
            "/paysupport - 付款支援\n"
            "/terms - 服務條款\n"
            "/reset - 清除對話狀態"
        )

    @router.message(Command("settings"))
    async def cmd_settings(message: types.Message, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("你還沒有完成註冊，請先使用 /start。")
            return

        verified = "✅ 已驗證" if user.age_verified_at else "❌ 未驗證"
        nsfw = "✅ 開啟" if user.nsfw_opt_in else "❌ 關閉（SFW）"
        await message.answer(
            f"⚙️ 目前設定\n"
            f"年齡驗證：{verified}\n"
            f"NSFW 內容：{nsfw}\n"
            f"語言：{user.locale}"
        )

    @router.message(Command("toggle_nsfw"))
    async def cmd_toggle_nsfw(message: types.Message, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("你還沒有完成註冊，請先使用 /start。")
            return
        if user.age_verified_at is None:
            await message.answer("請先完成年齡驗證：/start")
            return

        updated = await repo.toggle_nsfw(message.from_user.id)
        nsfw = "✅ 開啟" if updated.nsfw_opt_in else "❌ 關閉（SFW）"
        await message.answer(f"NSFW 內容已切換為：{nsfw}")

    @router.message(Command("reset"))
    async def cmd_reset(message: types.Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("已清除狀態。需要時請再輸入 /start。")

    @router.message(Command("voice_on"))
    async def cmd_voice_on(message: types.Message, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("請先完成註冊：/start")
            return
        await repo.set_voice_enabled(message.from_user.id, True)
        await message.answer("已開啟語音回覆 🎙️ 從現在起我會用文字回覆後，再補上一段語音。")

    @router.message(Command("voice_off"))
    async def cmd_voice_off(message: types.Message, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("請先完成註冊：/start")
            return
        await repo.set_voice_enabled(message.from_user.id, False)
        await message.answer("已關閉語音回覆 🔇 只會回文字囉。")

    @router.message(Command("voice_settings"))
    async def cmd_voice_settings(message: types.Message, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("請先完成註冊：/start")
            return
        enabled = "✅ 開啟" if user.voice_enabled else "❌ 關閉"
        await message.answer(
            f"🎙️ 語音設定\n"
            f"狀態：{enabled}\n"
            f"語音類別：{user.voice_slug}\n"
            f"語速：{user.voice_speed}\n"
            f"（用 /voice_list 看其他類別，/voice_set <類別> 切換）"
        )

    @router.message(Command("voice_list"))
    async def cmd_voice_list(message: types.Message, session: AsyncSession) -> None:
        voices = await VoiceRepository(session).list_active()
        if not voices:
            await message.answer("目前沒有可用的語音類別。")
            return
        lines = "\n".join(f"・<code>{v.slug}</code> — {v.name}" for v in voices)
        await message.answer(
            "🎙️ 可選語音類別：\n" + lines + "\n\n用 /voice_set <類別> 選擇喔～",
            parse_mode="HTML",
        )

    @router.message(Command("voice_set"))
    async def cmd_voice_set(message: types.Message, session: AsyncSession) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("用法：/voice_set <類別>（用 /voice_list 看有哪些）")
            return
        slug = parts[1].strip()
        vrepo = VoiceRepository(session)
        voice = await vrepo.get(slug)
        if voice is None or not voice.active:
            await message.answer(f"找不到語音類別「{slug}」，用 /voice_list 看看有哪些。")
            return
        repo = UserRepository(session)
        if await repo.get_by_telegram_id(message.from_user.id) is None:
            await message.answer("請先完成註冊：/start")
            return
        await repo.set_voice_slug(message.from_user.id, slug)
        await message.answer(f"已把語音類別換成「{voice.name}」🎙️")

    @router.message(Command("mood"))
    async def cmd_mood(message: types.Message, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("請先完成註冊：/start")
            return
        from orchestrator.persona import DEFAULT_PERSONA
        persona_slug = getattr(user, "active_persona_slug", DEFAULT_PERSONA)
        snapshot = await MoodService(session).get_mood(
            message.from_user.id, persona_slug
        )
        label_map = {
            "affection": "滿心喜歡你 💕",
            "playfulness": "想鬧你 😝",
            "longing": "好想你 🥺",
            "upset": "有點小委屈 😤",
            "neutral": "平靜地陪著你 😌",
        }
        await message.answer(
            f"此刻心情：{label_map.get(snapshot.dominant, snapshot.dominant)}\n"
            f"（{snapshot.phrase}）"
        )

    @router.message(Command("snooze"))
    async def cmd_snooze(message: types.Message, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("你還沒有完成註冊，請先使用 /start。")
            return
        await repo.set_proactive_opt_out(message.from_user.id, not user.proactive_opt_out)
        if user.proactive_opt_out:
            await message.answer("已重新開啟主動關心訊息 💌")
        else:
            await message.answer("已暫停主動關心訊息。想重新開啟再輸入一次 /snooze。")

    @router.message(Command("remind"))
    async def cmd_remind(message: types.Message, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("請先完成註冊：/start")
            return
        text = (message.text or "").replace("/remind", "", 1).strip()
        if not text:
            await message.answer("用法：/remind 明天下午三點繳電費")
            return
        try:
            parsed = await ReminderService(session).parse_and_create(
                user.telegram_id, text, timezone_str=user.timezone
            )
        except ReminderParseError as exc:
            await message.answer(str(exc))
            return
        local_due = parsed.due_at.astimezone(ZoneInfo(user.timezone))
        await message.answer(
            f"好～我記住了：「{parsed.content}」\n"
            f"提醒時間：{local_due.strftime('%Y-%m-%d %H:%M')}（{user.timezone}）\n"
            f"週期：{parsed.recurrence}"
        )

    @router.message(Command("reminders"))
    async def cmd_reminders(message: types.Message, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("請先完成註冊：/start")
            return
        reminders = await ReminderService(session).list_active(user.telegram_id)
        if not reminders:
            await message.answer("目前沒有進行中的提醒喔。")
            return
        lines = []
        for r in reminders:
            local = r.due_at.astimezone(ZoneInfo(user.timezone))
            lines.append(f"#{r.id} {r.content} — {local.strftime('%m/%d %H:%M')} ({r.recurrence})")
        await message.answer("📋 進行中的提醒：\n" + "\n".join(lines))

    @router.message(Command("cancel_reminder"))
    async def cmd_cancel_reminder(message: types.Message, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("請先完成註冊：/start")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().lstrip("#").isdigit():
            await message.answer("用法：/cancel_reminder <編號>")
            return
        reminder_id = int(parts[1].strip().lstrip("#"))
        cancelled = await ReminderService(session).cancel(reminder_id, user.telegram_id)
        if cancelled is None:
            await message.answer("找不到這個提醒，或已經取消了。")
            return
        await message.answer(f"已取消提醒：{cancelled.content}")

    @router.message(Command("birthday"))
    async def cmd_birthday(message: types.Message, session: AsyncSession) -> None:
        """Set the user's birthday: /birthday MM-DD  (e.g. /birthday 06-15)"""
        from shared.special_dates import SpecialDateService
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("請先完成註冊：/start")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("用法：/birthday MM-DD（例如 /birthday 06-15）")
            return
        raw = parts[1].strip()
        try:
            month_s, day_s = raw.split("-")
            month, day = int(month_s), int(day_s)
            if not (1 <= month <= 12 and 1 <= day <= 31):
                raise ValueError
        except ValueError:
            await message.answer("格式錯誤，請用 MM-DD，例如 /birthday 06-15")
            return
        await SpecialDateService(session).upsert(
            user_id=message.from_user.id,
            date_type="birthday",
            month=month,
            day=day,
            label="我的生日",
            recurrent=True,
        )
        await message.answer(
            f"✅ 記住了！你的生日是 {month:02d}/{day:02d}，到時候我會特別為你慶祝 🎂"
        )

    @router.message(Command("anniversary"))
    async def cmd_anniversary(message: types.Message, session: AsyncSession) -> None:
        """Set an anniversary: /anniversary MM-DD [description]"""
        from shared.special_dates import SpecialDateService
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("請先完成註冊：/start")
            return
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 2:
            await message.answer("用法：/anniversary MM-DD [說明]（例如 /anniversary 02-14 我們交往紀念日）")
            return
        raw = parts[1].strip()
        label = parts[2].strip() if len(parts) > 2 else "我們的紀念日"
        try:
            month_s, day_s = raw.split("-")
            month, day = int(month_s), int(day_s)
            if not (1 <= month <= 12 and 1 <= day <= 31):
                raise ValueError
        except ValueError:
            await message.answer("格式錯誤，請用 MM-DD，例如 /anniversary 02-14")
            return
        await SpecialDateService(session).upsert(
            user_id=message.from_user.id,
            date_type="anniversary",
            month=month,
            day=day,
            label=label,
            recurrent=True,
        )
        await message.answer(
            f"✅ 記住了！{label}（{month:02d}/{day:02d}），到時候我一定會好好紀念的 💕"
        )

    @router.message(Command("personas"))
    async def cmd_personas(message: types.Message, session: AsyncSession) -> None:
        """List available personas and show the current active one."""
        from orchestrator.persona import PERSONAS, DEFAULT_PERSONA
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        current_slug = getattr(user, "active_persona_slug", DEFAULT_PERSONA) if user else DEFAULT_PERSONA
        lines = []
        for slug, p in PERSONAS.items():
            marker = "✅" if slug == current_slug else "・"
            lines.append(f"{marker} <code>{slug}</code> — {p.name}（{p.personality[:20]}…）")
        await message.answer(
            "可選的女友人設：\n"
            + "\n".join(lines)
            + "\n\n用 /switch <代碼> 切換。目前是 "
            + (PERSONAS[current_slug].name if current_slug in PERSONAS else current_slug)
            + " 喔 💕"
        )

    @router.message(Command("switch"))
    async def cmd_switch(message: types.Message, session: AsyncSession) -> None:
        """Switch the active persona."""
        from orchestrator.persona import PERSONAS
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("用法：/switch <人設代碼>（用 /personas 查看代碼）")
            return
        slug = parts[1].strip().lower()
        if slug not in PERSONAS:
            await message.answer(f"找不到人設「{slug}」，用 /personas 看看有哪些。")
            return
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("請先完成註冊：/start")
            return
        user.active_persona_slug = slug
        await session.flush()
        p = PERSONAS[slug]
        await message.answer(
            f"好，現在換成 {p.name} 陪你了！\n"
            f"她的個性：{p.personality} 💕"
        )

    @router.message(Command("refer"))
    async def cmd_refer(message: types.Message) -> None:
        from shared.referral import make_deep_link
        from shared.config import get_settings
        bot_username = get_settings().bot_username
        if not bot_username:
            await message.answer(
                "推薦功能還在設定中，請稍後再試。"
            )
            return
        link = make_deep_link(bot_username, message.from_user.id)
        await message.answer(
            f"📣 邀請朋友加入，你每邀請一個成功啟用的朋友就可以獲得 20 點數！\n\n"
            f"你的專屬邀請連結：\n{link}\n\n"
            "分享給朋友，等他完成年齡驗證後點數就會自動入帳 💰",
            disable_web_page_preview=True,
        )

    return router
