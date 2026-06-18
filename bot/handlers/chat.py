from aiogram import F, Router, types
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.core import respond
from orchestrator.persona import get_persona
from shared.logging import get_logger
from shared.repositories.user_repo import UserRepository
from shared.voice import VoiceError, synthesize, voice_config_from_user

logger = get_logger("bot.chat")


def get_router() -> Router:
    router = Router()

    @router.message(F.text)
    async def handle_chat(message: types.Message, session: AsyncSession) -> None:
        """Handle normal text messages: persona + memory -> LLM -> reply."""
        if not message.text or message.text.startswith("/"):
            return

        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("我們還不認識呢，請先輸入 /start 完成註冊喔～")
            return
        if user.age_verified_at is None:
            await message.answer("請先完成年齡驗證：/start")
            return

        persona = get_persona()
        nsfw = user.nsfw_opt_in and user.age_verified_at is not None

        try:
            reply_text = await respond(
                message.from_user.id,
                message.text,
                persona,
                nsfw=nsfw,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("respond_failed", telegram_id=message.from_user.id, error=str(exc))
            await message.answer("嗯…我這邊有點恍神，可以再跟我說一次嗎？(´；ω；`)")
            return

        await message.answer(reply_text)

        if user.voice_enabled:
            try:
                voice_cfg = voice_config_from_user(user)
                voice_bytes = await synthesize(reply_text, voice_cfg)
                await message.answer_voice(
                    types.BufferedInputFile(voice_bytes, filename="voice.ogg")
                )
            except VoiceError as exc:
                logger.warning(
                    "voice_synthesis_failed",
                    telegram_id=message.from_user.id,
                    error=str(exc),
                )
                await message.answer("（語音訊息暫時發不出來，先用文字回你喔）")

    return router
