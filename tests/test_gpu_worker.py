"""Tests for the GPU media worker (task #8)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workers.gpu_worker import GPUWorker, VRAMManager
from workers.queue_client import MediaJob


@pytest.mark.asyncio
async def test_vram_manager_swaps_models():
    vram = VRAMManager()
    await vram.prepare("image")
    assert vram.loaded == "comfyui"
    await vram.prepare("video")
    assert vram.loaded == "video"
    await vram.prepare("image")
    assert vram.loaded == "comfyui"
    await vram.shutdown()
    assert vram.loaded is None


@pytest.mark.asyncio
async def test_worker_processes_photo_job_and_callbacks():
    worker = GPUWorker()
    worker.max_retries = 2

    job = MediaJob(
        job_id="job-1",
        user_id=100,
        job_type="image",
        workflow="t2i/test.json",
        params={"prompt": "test"},
        callback_url="http://localhost/callback",
    )

    with (
        patch("workers.gpu_worker.STUB_MODE", True),
        patch("workers.gpu_worker.redis_client"),
        patch("workers.gpu_worker.get_job", new=AsyncMock(return_value=job)),
        patch("workers.gpu_worker.mark_job_status", new=AsyncMock()) as mock_mark,
        patch("workers.gpu_worker.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
        mock_client_cls.return_value = mock_client

        await worker._handle_job("job-1")

    mock_mark.assert_awaited()
    args = mock_mark.await_args
    assert args.args[1] == "done"
    mock_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_retries_then_dead_letters():
    worker = GPUWorker()
    worker.max_retries = 1

    job = MediaJob(
        job_id="job-2",
        user_id=100,
        job_type="image",
        workflow="t2i/test.json",
        params={},
        callback_url="",
    )

    with (
        patch("workers.gpu_worker.redis_client"),
        patch("workers.gpu_worker.get_job", new=AsyncMock(return_value=job)),
        patch("workers.gpu_worker.mark_job_status", new=AsyncMock()),
        patch("workers.gpu_worker.requeue_job", new=AsyncMock()) as mock_requeue,
        patch("workers.gpu_worker.dead_letter", new=AsyncMock()) as mock_dead,
        patch.object(worker.vram, "prepare", new=AsyncMock()),
        patch("workers.gpu_worker.PROCESSORS", {"image": MagicMock(run=AsyncMock(side_effect=RuntimeError("boom")))}),
    ):
        await worker._handle_job("job-2")

    assert job.retry_count == 1
    # max_retries=1 means first failure -> dead letter.
    mock_dead.assert_awaited_once()
    mock_requeue.assert_not_awaited()
