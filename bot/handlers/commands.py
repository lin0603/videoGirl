from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.onboarding import start_onboarding
from bot.states import OnboardingState
from shared.logging import get_logger
from shared.repositories.user_repo import UserRepository

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

    return router
