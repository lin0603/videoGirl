from aiogram import F, Router, types
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.core import respond
from orchestrator.persona import get_persona
from shared.image_gen import is_photo_request, request_photo
from shared.quota import check_queue_backpressure, check_quota, increment_quota
from shared.video_gen import build_source_image_url, is_video_request, request_video
from shared.logging import get_logger
from shared.mood import MoodService, format_mood_for_prompt
from shared.safety import check_prompt, refusal_message
from shared.repositories.subscription_repo import EntitlementService
from shared.repositories.user_repo import UserRepository
from shared.repositories.voice_repo import VoiceRepository
from shared.voice import VoiceConfig, VoiceError, synthesize

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

        # Hard safety check — block illegal/minor content before any LLM call.
        safety = check_prompt(message.text, user_id=message.from_user.id)
        if not safety.allowed:
            await message.answer(refusal_message())
            return

        persona = get_persona(getattr(user, "active_persona_slug", None))
        entitlements = EntitlementService(session)
        nsfw_allowed = await entitlements.nsfw_allowed(user)
        nsfw = user.nsfw_opt_in and user.age_verified_at is not None and nsfw_allowed

        if user.nsfw_opt_in and not nsfw_allowed:
            await message.answer(
                "你已開啟 NSFW，但需要 VIP 訂閱才能解鎖成人內容喔。\n"
                "輸入 /subscribe 訂閱 VIP 月方案 💎"
            )

        # Update companion mood and inject it into the system prompt.
        mood_phrase = await MoodService(session).process_chat_message(
            message.from_user.id, persona.slug, message.text
        )
        mood_context = format_mood_for_prompt(mood_phrase)

        try:
            reply_text = await respond(
                message.from_user.id,
                message.text,
                persona,
                nsfw=nsfw,
                mood_context=mood_context,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("respond_failed", telegram_id=message.from_user.id, error=str(exc))
            await message.answer("嗯…我這邊有點恍神，可以再跟我說一次嗎？(´；ω；`)")
            return

        await message.answer(reply_text)

        # Detect photo-request intent; enqueue async image generation.
        if is_photo_request(message.text):
            photo_quota = await check_quota(message.from_user.id, "image")
            if not photo_quota.allowed:
                await message.answer(photo_quota.reason or "今天照片已達上限，明天再傳喔 📸")
            else:
                job_id = await request_photo(message.from_user.id, nsfw=nsfw)
                if job_id:
                    await increment_quota(message.from_user.id, "image")
                    await message.answer("好的，稍等一下，我去拍一張給你 📸")
                else:
                    logger.debug("photo_request_skipped_no_callback", telegram_id=message.from_user.id)

        # Detect video-request intent (lower priority queue, fire-and-forget).
        if is_video_request(message.text):
            video_quota = await check_quota(message.from_user.id, "video")
            bp = await check_queue_backpressure()
            if not video_quota.allowed:
                await message.answer(video_quota.reason or "今天影片已達上限，明天再試 🎬")
            elif not bp.allowed:
                await message.answer(bp.reason or "GPU 目前忙碌，請稍後再試 🎬")
            else:
                source_url = await build_source_image_url(message.from_user.id)
                if source_url:
                    video_job_id = await request_video(
                        message.from_user.id,
                        source_image_url=source_url,
                        nsfw=nsfw,
                    )
                    if video_job_id:
                        await increment_quota(message.from_user.id, "video")
                        await message.answer(
                            "好，幫你生成一段小影片，需要幾分鐘，做好了我會傳給你 🎬"
                        )
                    else:
                        logger.debug("video_request_no_callback", telegram_id=message.from_user.id)
                else:
                    # No cached source photo — ask user to request a photo first.
                    await message.answer(
                        "要幫你生成影片，先傳一張照片給你～你可以先跟我說「傳照片給我」😊"
                    )

        if user.voice_enabled:
            try:
                # Resolve the user's chosen voice category from the admin catalog.
                voice_row = await VoiceRepository(session).get(user.voice_slug)
                voice_cfg = VoiceConfig(
                    provider="breezevoice",
                    speed=user.voice_speed * (voice_row.tempo if voice_row else 1.0),
                    reference_audio_path=voice_row.reference_audio_path if voice_row else None,
                    reference_transcript=voice_row.reference_transcript if voice_row else None,
                )
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
