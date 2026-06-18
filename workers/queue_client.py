"""
Coolify-side async queue client.

Enqueues media jobs into Redis priority queues (photo > video).
Results arrive via HTTP callback from the 4090 worker to /internal/media_done.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

PHOTO_QUEUE = "media:photo"
VIDEO_QUEUE = "media:video"
DEAD_QUEUE = "media:dead"
_JOB_PREFIX = "mediajob:"
_JOB_TTL = 86400  # 1 day


@dataclass
class MediaJob:
    job_id: str
    user_id: int
    job_type: str  # "image" | "video"
    workflow: str  # relative to infra/comfyui/workflows/, e.g. "t2i/zimage-t2i.api.json"
    params: dict[str, Any]  # ComfyUI node overrides: {"<node_id>.<input>": value}
    callback_url: str
    status: str = "queued"  # queued | started | done | failed | dead
    retry_count: int = 0
    error: str | None = None


async def _get_redis():
    from shared.redis import get_redis
    return await get_redis()


async def enqueue_image_job(
    *,
    user_id: int,
    workflow: str,
    params: dict[str, Any],
    callback_url: str,
) -> str:
    """Enqueue a photo-generation job (high-priority lane). Returns job_id."""
    job_id = str(uuid.uuid4())
    job = MediaJob(
        job_id=job_id,
        user_id=user_id,
        job_type="image",
        workflow=workflow,
        params=params,
        callback_url=callback_url,
    )
    r = await _get_redis()
    pipe = r.pipeline()
    pipe.set(_JOB_PREFIX + job_id, json.dumps(asdict(job)), ex=_JOB_TTL)
    pipe.rpush(PHOTO_QUEUE, job_id)
    await pipe.execute()
    return job_id


async def enqueue_video_job(
    *,
    user_id: int,
    workflow: str,
    params: dict[str, Any],
    callback_url: str,
) -> str:
    """Enqueue a video-generation job (lower-priority lane). Returns job_id."""
    job_id = str(uuid.uuid4())
    job = MediaJob(
        job_id=job_id,
        user_id=user_id,
        job_type="video",
        workflow=workflow,
        params=params,
        callback_url=callback_url,
    )
    r = await _get_redis()
    pipe = r.pipeline()
    pipe.set(_JOB_PREFIX + job_id, json.dumps(asdict(job)), ex=_JOB_TTL)
    pipe.rpush(VIDEO_QUEUE, job_id)
    await pipe.execute()
    return job_id


async def get_job(job_id: str) -> MediaJob | None:
    r = await _get_redis()
    raw = await r.get(_JOB_PREFIX + job_id)
    if raw is None:
        return None
    return MediaJob(**json.loads(raw))


async def update_job(job: MediaJob) -> None:
    r = await _get_redis()
    await r.set(_JOB_PREFIX + job.job_id, json.dumps(asdict(job)), ex=_JOB_TTL)


async def queue_lengths() -> dict[str, int]:
    r = await _get_redis()
    photo = await r.llen(PHOTO_QUEUE)
    video = await r.llen(VIDEO_QUEUE)
    dead = await r.llen(DEAD_QUEUE)
    return {"photo": photo, "video": video, "dead": dead}
