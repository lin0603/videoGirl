"""GPU media worker (task #8).

Runs on the rented 4090 (or locally in stub mode). Pulls jobs from Redis with
photo priority, swaps ComfyUI / video models in VRAM, and POSTs results back
to the Coolify callback endpoint.
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

from shared.comfyui_gateway import GatewayError
from shared.config import get_settings
from shared.logging import configure_logging, get_logger
from shared.redis import redis_client
from workers.queue_client import (
    DEAD_QUEUE,
    PHOTO_QUEUE,
    VIDEO_QUEUE,
    MediaJob,
    dead_letter,
    get_job,
    mark_job_status,
    requeue_job,
)

configure_logging()
logger = get_logger("workers.gpu_worker")

STUB_MODE = os.environ.get("GPU_WORKER_STUB", "0") == "1"


class VRAMManager:
    """Tracks the currently-loaded model and swaps when needed.

    In stub mode it only logs. In production this calls ComfyUI / systemd
    services to load and unload model checkpoints so a 24GB card can fit one
    big model at a time.
    """

    def __init__(self) -> None:
        self.loaded: str | None = None

    async def prepare(self, job_type: str) -> None:
        target = "comfyui" if job_type == "image" else "video"
        if self.loaded == target:
            return
        if self.loaded is not None:
            await self._unload(self.loaded)
        await self._load(target)
        self.loaded = target

    async def shutdown(self) -> None:
        if self.loaded is not None:
            await self._unload(self.loaded)
            self.loaded = None

    async def _load(self, target: str) -> None:
        if STUB_MODE:
            logger.info("vram_load_stub", target=target)
            await asyncio.sleep(0.01)
            return
        logger.info("vram_load", target=target)
        # TODO: call ComfyUI/custom endpoint to load the target pipeline.

    async def _unload(self, target: str) -> None:
        if STUB_MODE:
            logger.info("vram_unload_stub", target=target)
            await asyncio.sleep(0.01)
            return
        logger.info("vram_unload", target=target)
        # TODO: call ComfyUI/custom endpoint to free the target pipeline.


class MediaProcessor(ABC):
    @abstractmethod
    async def run(self, job: MediaJob) -> str:
        """Run the job and return a result URL."""


class ImageProcessor(MediaProcessor):
    async def run(self, job: MediaJob) -> str:
        if STUB_MODE:
            logger.info("image_process_stub", job_id=job.job_id)
            await asyncio.sleep(0.01)
            return f"https://example.com/stub-image-{job.job_id}.jpg"

        # task #10：照片優先走 gateway capability；無 capability 的 legacy 任務保留 NotImplementedError。
        if job.capability:
            from shared.comfyui_gateway import generate

            result = await generate(
                job.capability,
                job.gen_params or {},
                job.images or None,
                wait=True,
                timeout=600.0,
            )
            outputs = result.get("outputs") or []
            if not outputs:
                raise GatewayError(
                    "Gateway job produced no outputs",
                    detail=result.get("error"),
                )
            return outputs[0]["url"]

        raise NotImplementedError("ComfyUI integration not configured")


class VideoProcessor(MediaProcessor):
    async def run(self, job: MediaJob) -> str:
        if STUB_MODE:
            logger.info("video_process_stub", job_id=job.job_id)
            await asyncio.sleep(0.02)
            return f"https://example.com/stub-video-{job.job_id}.mp4"
        # TODO: call video generation pipeline with job.params.
        raise NotImplementedError("Video pipeline integration not configured")


PROCESSORS: dict[str, MediaProcessor] = {
    "image": ImageProcessor(),
    "video": VideoProcessor(),
}


class GPUWorker:
    def __init__(self) -> None:
        self.vram = VRAMManager()
        self.settings = get_settings()
        self.max_retries = max(1, self.settings.media_max_retries)
        self._running = True

    async def run(self) -> None:
        logger.info("gpu_worker_started", stub=STUB_MODE)
        while self._running:
            try:
                job_id = await self._pop_job()
                if job_id is None:
                    continue
                await self._handle_job(job_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("gpu_worker_loop_error", error=str(exc))
                await asyncio.sleep(1)
        await self.vram.shutdown()
        logger.info("gpu_worker_stopped")

    async def stop(self) -> None:
        self._running = False

    async def _pop_job(self) -> str | None:
        r = await redis_client.connect()
        # BLPOP checks PHOTO_QUEUE first, then VIDEO_QUEUE, giving photo priority.
        result = await r.blpop([PHOTO_QUEUE, VIDEO_QUEUE], timeout=5)
        if result is None:
            return None
        return result[1]

    async def _handle_job(self, job_id: str) -> None:
        job = await get_job(job_id)
        if job is None:
            logger.error("job_not_found", job_id=job_id)
            return

        logger.info("job_started", job_id=job_id, type=job.job_type)
        await mark_job_status(job, "started")

        try:
            await self.vram.prepare(job.job_type)
            processor = PROCESSORS.get(job.job_type)
            if processor is None:
                raise ValueError(f"Unknown job type: {job.job_type}")
            result_url = await processor.run(job)
        except Exception as exc:
            logger.exception("job_failed", job_id=job_id, error=str(exc))
            await self._retry_or_dead_letter(job, str(exc))
            return

        await mark_job_status(job, "done", result_url=result_url)
        await self._send_callback(job, result_url)
        logger.info("job_done", job_id=job_id, result_url=result_url)

    async def _retry_or_dead_letter(self, job: MediaJob, error: str) -> None:
        job.retry_count += 1
        if job.retry_count >= self.max_retries:
            await dead_letter(job, error)
            logger.warning("job_dead_lettered", job_id=job.job_id, retries=job.retry_count)
        else:
            # Requeue at the front so it gets another chance quickly.
            await requeue_job(job, front=True)
            logger.info("job_requeued", job_id=job.job_id, retry=job.retry_count)

    async def _send_callback(self, job: MediaJob, result_url: str) -> None:
        callback_url = job.callback_url or self.settings.media_callback_url
        if not callback_url:
            logger.warning("no_callback_url", job_id=job.job_id)
            return
        payload: dict[str, Any] = {
            "job_id": job.job_id,
            "user_id": job.user_id,
            "job_type": job.job_type,
            "status": "done",
            "result_url": result_url,
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.settings.media_callback_secret:
            headers["Authorization"] = f"Bearer {self.settings.media_callback_secret}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(callback_url, json=payload, headers=headers)
                resp.raise_for_status()
        except Exception as exc:
            logger.error("callback_failed", job_id=job.job_id, error=str(exc))


def main() -> None:
    worker = GPUWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("gpu_worker_interrupted")


if __name__ == "__main__":
    main()
