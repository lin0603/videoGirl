"""
Image generation service — enqueues ComfyUI photo jobs for a user.

Uses the GPU queue (task #8) so photo delivery is async:
  1. Bot detects photo intent → calls request_photo()
  2. Worker picks up the job, runs ComfyUI, POSTs result to callback
  3. Callback endpoint delivers the image via sendPhoto
"""
from __future__ import annotations

import random
import re

from shared.config import get_settings
from shared.safety import check_image_prompt
from workers.queue_client import enqueue_image_job

_PHOTO_INTENT_RE = re.compile(
    r"(傳照片|寄照片|照片|自拍|selfie|selfies|看你|你的照片|傳一張|給我看|秀一下"
    r"|秀照片|讓我看看|拍一張|想看|拍個照|拍張照|show me|photo|pic)",
    re.IGNORECASE,
)

# Positive prompt templates — node 4.prompt in zimage-t2i.api.json
_SFW_PROMPT = (
    "photorealistic portrait photo of a beautiful young Taiwanese woman, "
    "natural smile, casual stylish outfit, indoor modern setting, "
    "professional lighting, sharp focus, high quality, 1girl, solo"
)
_NSFW_PROMPT = (
    "photorealistic intimate portrait of a beautiful young Taiwanese woman, "
    "seductive expression, bedroom, soft natural lighting, high quality, "
    "1girl, solo, nsfw, topless, TaiwanDollLikeness"
)


def is_photo_request(text: str) -> bool:
    return bool(_PHOTO_INTENT_RE.search(text))


async def request_photo(
    user_id: int,
    *,
    nsfw: bool = False,
    extra_context: str = "",
) -> str | None:
    """
    Enqueue a photo-generation job.
    Returns job_id if queued, None if media_callback_url is not configured.
    """
    settings = get_settings()
    if not settings.media_callback_url:
        return None

    base = _NSFW_PROMPT if nsfw else _SFW_PROMPT
    prompt = f"{base}, {extra_context}".rstrip(", ") if extra_context else base

    # Safety check on the final prompt (catches injected illegal terms).
    if not check_image_prompt(prompt, user_id=user_id).allowed:
        return None

    return await enqueue_image_job(
        user_id=user_id,
        workflow="t2i/zimage-t2i.api.json",
        params={
            "4.prompt": prompt,
            "6.seed": random.randint(1, 2**31 - 1),
        },
        callback_url=settings.media_callback_url,
    )
