from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.onboarding import start_onboarding
from bot.states import OnboardingState
from shared.logging import get_logger
from shared.mood import MoodService
from shared.repositories.user_repo import UserRepository
from shared.repositories.voice_repo import VoiceRepository

logger = get_logger("bot.commands")


def get_router() -> Router:
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
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
            "/voice_set <類別> - 選擇語音類別\n"
            "/products - 查看 Stars 數位商品\n"
            "/buy <商品代碼> - 開立 Telegram Stars 發票\n"
            "/subscribe - 訂閱 VIP 月方案\n"
            "/vip_status - 查看 VIP 狀態\n"
            "/cancel_vip - 取消 VIP 自動續訂\n"
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
        snapshot = await MoodService(session).get_mood(
            message.from_user.id, "xiaorou"
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

    return router
