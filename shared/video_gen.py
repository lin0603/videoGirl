"""
Image-to-video generation service (task #14).

Enqueues an I2V job on the media:video queue (lowest priority).
The 4090 worker picks it up when idle (after all photo jobs are done).

Workflow: wan22-i2v-q4km.api.json (Wan2.2 GGUF Q4_K_M, ~13GB VRAM).
Source image is uploaded to ComfyUI via the worker before submission.
"""
from __future__ import annotations

import random
import re

from shared.config import get_settings
from workers.queue_client import enqueue_video_job

_VIDEO_INTENT_RE = re.compile(
    r"(影片|動影片|動態|給我看影片|傳影片|視頻|動圖|錄影|動態照|影片照|"
    r"video|videos|clip|clips|gif|動一下|動起來|活起來)",
    re.IGNORECASE,
)

# Default I2V workflow (Q4_K_M — good balance of speed vs quality on 4090 48GB).
_WORKFLOW_I2V = "i2v/wan22-i2v-q4km.api.json"

# Positive/negative text prompts injected into the Wan2.2 CLIP encoder (node 89/93).
_SFW_POSITIVE = (
    "beautiful young Taiwanese woman, gentle natural movement, "
    "soft lighting, cinematic, smooth motion, 4k"
)
_NSFW_POSITIVE = (
    "beautiful young Taiwanese woman, sensual natural movement, "
    "nsfw, soft lighting, cinematic, smooth motion, 4k"
)
_NEGATIVE = (
    "low quality, blurry, bad anatomy, watermark, text, distorted, "
    "worst quality, flickering, stuttering"
)


def is_video_request(text: str) -> bool:
    return bool(_VIDEO_INTENT_RE.search(text))


async def build_source_image_url(user_id: int) -> str | None:
    """
    Build the URL the 4090 worker can use to fetch the last generated photo.
    Returns None if no photo is cached or callback URL is not configured.
    """
    from shared.config import get_settings
    settings = get_settings()
    base = settings.media_callback_url
    if not base:
        return None
    # Strip the path; use the Coolify host with the internal photo endpoint.
    from urllib.parse import urlparse
    parsed = urlparse(base)
    host = f"{parsed.scheme}://{parsed.netloc}"
    return f"{host}/internal/photo/{user_id}"


async def request_video(
    user_id: int,
    *,
    source_image_url: str,
    nsfw: bool = False,
    width: int = 832,
    height: int = 480,
    num_frames: int = 49,
) -> str | None:
    """
    Enqueue an I2V job using the given source image URL.

    The worker will fetch the image, upload it to ComfyUI, then generate the clip.
    Returns job_id if queued, None if media pipeline is not configured.
    """
    settings = get_settings()
    if not settings.media_callback_url:
        return None

    positive = _NSFW_POSITIVE if nsfw else _SFW_POSITIVE
    seed = random.randint(1, 2**31 - 1)

    return await enqueue_video_job(
        user_id=user_id,
        workflow=_WORKFLOW_I2V,
        params={
            # Source image — worker fetches this URL and uploads to ComfyUI.
            "_source_image_url": source_image_url,
            "_source_image_node": "97",
            # Text conditioning (node 89 = positive, 93 = negative).
            "89.text": positive,
            "93.text": _NEGATIVE,
            # Video dimensions and length.
            "98.width": width,
            "98.height": height,
            "98.length": num_frames,
            # Sampler seed (node 85 = first KSamplerAdvanced pass).
            "85.noise_seed": seed,
        },
        callback_url=settings.media_callback_url,
    )
