from datetime import datetime

from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import nsfw_opt_in_keyboard
from bot.states import OnboardingState
from shared.logging import get_logger
from shared.repositories.user_repo import UserRepository

logger = get_logger("bot.onboarding")


async def start_onboarding(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    repo = UserRepository(session)
    user = await repo.create_or_update(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        display_name=message.from_user.full_name,
    )
    if user.age_verified_at is not None:
        await state.clear()
        await message.answer(
            "👋 歡迎回來！如果之後想更改 NSFW 設定，請使用 /toggle_nsfw。"
        )
        return

    await message.answer(
        "🔞 本 bot 可能包含成人內容。請先輸入你的出生年份（例如 1995）以確認你已年滿 18 歲。"
    )


def get_router() -> Router:
    router = Router()

    @router.message(OnboardingState.age_gate)
    async def process_age_gate(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
        year_text = message.text.strip()
        try:
            birth_year = int(year_text)
        except ValueError:
            await message.answer("請輸入正確的出生年份，例如 1995。")
            return

        current_year = datetime.utcnow().year
        age = current_year - birth_year

        if age < 18:
            logger.warning(
                "age_gate_rejected",
                telegram_id=message.from_user.id,
                birth_year=birth_year,
                age=age,
            )
            await message.answer(
                "你尚未滿 18 歲，無法使用本服務。"
            )
            await state.clear()
            return

        repo = UserRepository(session)
        await repo.set_age_verified(message.from_user.id)
        logger.info(
            "age_gate_verified",
            telegram_id=message.from_user.id,
            birth_year=birth_year,
            age=age,
        )

        await state.set_state(OnboardingState.nsfw_opt_in)
        await message.answer(
            "✅ 年齡驗證通過。請選擇是否開啟成人內容（NSFW）？預設為關閉。",
            reply_markup=nsfw_opt_in_keyboard(),
        )

    @router.callback_query(OnboardingState.nsfw_opt_in)
    async def process_nsfw_choice(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
        repo = UserRepository(session)
        opt_in = callback.data == "nsfw_yes"
        await repo.set_nsfw(callback.from_user.id, opt_in)
        logger.info(
            "nsfw_choice",
            telegram_id=callback.from_user.id,
            nsfw_opt_in=opt_in,
        )

        await callback.answer()
        await state.clear()

        if opt_in:
            await callback.message.edit_text(
                "你已開啟 NSFW 內容。隨時可用 /toggle_nsfw 切換，或用 /settings 查看目前設定。"
            )
        else:
            await callback.message.edit_text(
                "你選擇保持 SFW。隨時可用 /toggle_nsfw 切換，或用 /settings 查看目前設定。"
            )

    return router
