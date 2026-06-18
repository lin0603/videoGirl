"""Per-user daily media quotas and queue backpressure (task #16).

Uses Redis counters with 24-hour TTL:
    media:quota:{user_id}:{job_type}   → daily count
    media:queue:depth:{queue_name}     → read from Redis list length

Tier limits are configured via settings (configurable per free/VIP later).
All quota checks are non-blocking; failures are logged, not propagated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from shared.logging import get_logger
from shared.redis import get_redis

JobType = Literal["image", "video", "voice"]

_QUOTA_KEY_FMT = "media:quota:{user_id}:{job_type}"
_QUEUE_DEPTH_FREE_IMAGE = 10   # free tier daily photo limit
_QUEUE_DEPTH_FREE_VIDEO = 2    # free tier daily video limit
_QUEUE_DEPTH_FREE_VOICE = 20   # free tier daily voice limit
_QUEUE_DEPTH_VIP_IMAGE = 50
_QUEUE_DEPTH_VIP_VIDEO = 10
_QUEUE_DEPTH_VIP_VOICE = 100

# Max number of pending video jobs in the queue (backpressure gate).
_MAX_PENDING_VIDEO_JOBS = 5
_VIDEO_QUEUE_KEY = "media:video"

_QUOTA_TTL = 86_400  # 24 h

_logger = get_logger("quota")


@dataclass
class QuotaCheck:
    allowed: bool
    reason: str | None = None


def _daily_limit(job_type: JobType, *, vip: bool) -> int:
    if vip:
        return {
            "image": _QUEUE_DEPTH_VIP_IMAGE,
            "video": _QUEUE_DEPTH_VIP_VIDEO,
            "voice": _QUEUE_DEPTH_VIP_VOICE,
        }[job_type]
    return {
        "image": _QUEUE_DEPTH_FREE_IMAGE,
        "video": _QUEUE_DEPTH_FREE_VIDEO,
        "voice": _QUEUE_DEPTH_FREE_VOICE,
    }[job_type]


async def check_quota(user_id: int, job_type: JobType, *, vip: bool = False) -> QuotaCheck:
    """Return QuotaCheck.allowed=True if the user is under their daily limit."""
    try:
        r = await get_redis()
        key = _QUOTA_KEY_FMT.format(user_id=user_id, job_type=job_type)
        count = await r.get(key)
        current = int(count) if count else 0
        limit = _daily_limit(job_type, vip=vip)
        if current >= limit:
            _logger.info(
                "quota_exceeded",
                user_id=user_id,
                job_type=job_type,
                current=current,
                limit=limit,
            )
            return QuotaCheck(
                allowed=False,
                reason=f"每日{job_type}上限 {limit} 次已達，明天再試試喔 😊",
            )
        return QuotaCheck(allowed=True)
    except Exception as exc:
        # Fail open — never block user on Redis errors.
        _logger.warning("quota_check_failed", user_id=user_id, job_type=job_type, error=str(exc))
        return QuotaCheck(allowed=True)


async def increment_quota(user_id: int, job_type: JobType) -> None:
    """Increment daily usage counter after a job is successfully enqueued."""
    try:
        r = await get_redis()
        key = _QUOTA_KEY_FMT.format(user_id=user_id, job_type=job_type)
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, _QUOTA_TTL)
        await pipe.execute()
    except Exception as exc:
        _logger.warning("quota_increment_failed", user_id=user_id, job_type=job_type, error=str(exc))


async def check_queue_backpressure() -> QuotaCheck:
    """Gate new video jobs when the pending queue is full."""
    try:
        r = await get_redis()
        depth = await r.llen(_VIDEO_QUEUE_KEY)
        if depth >= _MAX_PENDING_VIDEO_JOBS:
            _logger.info("video_queue_backpressure", depth=depth)
            return QuotaCheck(
                allowed=False,
                reason="GPU 目前很忙，影片佇列已滿，請稍後再試 🎬",
            )
        return QuotaCheck(allowed=True)
    except Exception as exc:
        _logger.warning("backpressure_check_failed", error=str(exc))
        return QuotaCheck(allowed=True)


async def get_usage(user_id: int, job_type: JobType) -> int:
    """Return current daily usage count (for admin/debug)."""
    try:
        r = await get_redis()
        key = _QUOTA_KEY_FMT.format(user_id=user_id, job_type=job_type)
        val = await r.get(key)
        return int(val) if val else 0
    except Exception:
        return 0
