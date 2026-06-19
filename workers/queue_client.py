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
    workflow: str = ""  # relative to infra/comfyui/workflows/, e.g. "t2i/zimage-t2i.api.json"
    params: dict[str, Any] = field(default_factory=dict)  # 原生 ComfyUI 節點覆寫（影片仍用）
    callback_url: str = ""
    status: str = "queued"  # queued | started | done | failed | dead
    retry_count: int = 0
    error: str | None = None
    # task #10：照片改走 gateway capability，與舊 workflow/params 向後相容。
    capability: str | None = None
    gen_params: dict[str, Any] = field(default_factory=dict)
    images: dict[str, str] = field(default_factory=dict)


async def _get_redis():
    from shared.redis import get_redis
    return await get_redis()


async def enqueue_image_job(
    *,
    user_id: int,
    workflow: str = "",
    params: dict[str, Any] | None = None,
    callback_url: str,
    capability: str | None = None,
    gen_params: dict[str, Any] | None = None,
    images: dict[str, str] | None = None,
) -> str:
    """
    Enqueue a photo-generation job (high-priority lane). Returns job_id.

    task #10：新增 capability/gen_params/images 以支援 gateway；
    未提供時仍走舊的 workflow/params，保持向後相容。
    """
    job_id = str(uuid.uuid4())
    job = MediaJob(
        job_id=job_id,
        user_id=user_id,
        job_type="image",
        workflow=workflow,
        params=params or {},
        callback_url=callback_url,
        capability=capability,
        gen_params=gen_params or {},
        images=images or {},
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


async def requeue_job(job: MediaJob, *, front: bool = False) -> None:
    """Push a job back to its type queue (front=True inserts at the head)."""
    job.status = "queued"
    r = await _get_redis()
    await update_job(job)
    queue = PHOTO_QUEUE if job.job_type == "image" else VIDEO_QUEUE
    if front:
        await r.lpush(queue, job.job_id)
    else:
        await r.rpush(queue, job.job_id)


async def dead_letter(job: MediaJob, error: str) -> None:
    """Move a permanently failed job to the dead-letter queue."""
    job.status = "dead"
    job.error = error
    r = await _get_redis()
    await update_job(job)
    await r.rpush(DEAD_QUEUE, job.job_id)


async def mark_job_status(job: MediaJob, status: str, *, result_url: str | None = None, error: str | None = None) -> None:
    job.status = status
    if result_url is not None:
        job.params["result_url"] = result_url
    if error is not None:
        job.error = error
    await update_job(job)


async def queue_lengths() -> dict[str, int]:
    r = await _get_redis()
    photo = await r.llen(PHOTO_QUEUE)
    video = await r.llen(VIDEO_QUEUE)
    dead = await r.llen(DEAD_QUEUE)
    return {"photo": photo, "video": video, "dead": dead}
