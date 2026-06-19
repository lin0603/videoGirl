"""Tests for the GPU media queue (task #8)."""
from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workers.comfyui_runner import apply_params, ComfyUIError
from workers.media_tasks import execute_job
from workers.queue_client import (
    DEAD_QUEUE,
    PHOTO_QUEUE,
    VIDEO_QUEUE,
    MediaJob,
    enqueue_image_job,
    enqueue_video_job,
    get_job,
    queue_lengths,
    update_job,
)


# ---------------------------------------------------------------------------
# queue_client (async, mocked Redis)
# ---------------------------------------------------------------------------

class _FakeRedis:
    """Minimal async Redis stand-in for queue_client tests."""

    def __init__(self):
        self._store: dict[str, str] = {}
        self._lists: dict[str, list] = {}

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value, ex=None):
        self._store[key] = value

    async def llen(self, key):
        return len(self._lists.get(key, []))

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeRedis):
        self._r = redis
        self._cmds: list = []

    def set(self, key, value, ex=None):
        self._cmds.append(("set", key, value))
        return self

    def rpush(self, queue, value):
        self._cmds.append(("rpush", queue, value))
        return self

    async def execute(self):
        for cmd in self._cmds:
            if cmd[0] == "set":
                self._r._store[cmd[1]] = cmd[2]
            elif cmd[0] == "rpush":
                # cmd = ("rpush", queue_name, value)
                self._r._lists.setdefault(cmd[1], []).append(cmd[2])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.execute()


@pytest.fixture
def fake_redis():
    return _FakeRedis()


@pytest.mark.asyncio
async def test_enqueue_image_job_stores_and_queues(fake_redis):
    with patch("workers.queue_client._get_redis", new=AsyncMock(return_value=fake_redis)):
        job_id = await enqueue_image_job(
            user_id=123,
            workflow="t2i/zimage-t2i.api.json",
            params={"6.text": "a girl"},
            callback_url="http://coolify/internal/media_done",
        )

    assert f"mediajob:{job_id}" in fake_redis._store
    stored = json.loads(fake_redis._store[f"mediajob:{job_id}"])
    assert stored["user_id"] == 123
    assert stored["job_type"] == "image"
    assert stored["status"] == "queued"
    assert job_id in fake_redis._lists.get(PHOTO_QUEUE, [])
    assert job_id not in fake_redis._lists.get(VIDEO_QUEUE, [])


@pytest.mark.asyncio
async def test_enqueue_video_job_uses_video_queue(fake_redis):
    with patch("workers.queue_client._get_redis", new=AsyncMock(return_value=fake_redis)):
        job_id = await enqueue_video_job(
            user_id=456,
            workflow="i2v/ltx23-10eros-q3ks-small.api.json",
            params={},
            callback_url="http://coolify/internal/media_done",
        )

    assert job_id in fake_redis._lists.get(VIDEO_QUEUE, [])
    assert job_id not in fake_redis._lists.get(PHOTO_QUEUE, [])


@pytest.mark.asyncio
async def test_enqueue_image_job_stores_gateway_capability(fake_redis):
    with patch("workers.queue_client._get_redis", new=AsyncMock(return_value=fake_redis)):
        job_id = await enqueue_image_job(
            user_id=111,
            callback_url="http://coolify/internal/media_done",
            capability="t2i",
            gen_params={"prompt": "a girl"},
            images={},
        )

    stored = json.loads(fake_redis._store[f"mediajob:{job_id}"])
    assert stored["capability"] == "t2i"
    assert stored["gen_params"]["prompt"] == "a girl"
    assert stored["images"] == {}
    assert stored["job_type"] == "image"
    assert job_id in fake_redis._lists.get(PHOTO_QUEUE, [])


@pytest.mark.asyncio
async def test_get_job_returns_none_for_missing(fake_redis):
    with patch("workers.queue_client._get_redis", new=AsyncMock(return_value=fake_redis)):
        result = await get_job("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_get_job_roundtrip(fake_redis):
    with patch("workers.queue_client._get_redis", new=AsyncMock(return_value=fake_redis)):
        job_id = await enqueue_image_job(
            user_id=789,
            workflow="t2i/zimage-t2i.api.json",
            params={},
            callback_url="http://coolify/internal/media_done",
        )
        job = await get_job(job_id)

    assert job is not None
    assert job.user_id == 789
    assert job.status == "queued"


# ---------------------------------------------------------------------------
# comfyui_runner.apply_params
# ---------------------------------------------------------------------------

def test_apply_params_modifies_matching_node():
    wf = {"6": {"inputs": {"text": "original", "seed": 0}}}
    result = apply_params(wf, {"6.text": "new prompt", "6.seed": 42})
    assert result["6"]["inputs"]["text"] == "new prompt"
    assert result["6"]["inputs"]["seed"] == 42


def test_apply_params_ignores_unknown_node():
    wf = {"6": {"inputs": {"text": "original"}}}
    result = apply_params(wf, {"99.text": "irrelevant"})
    assert result["6"]["inputs"]["text"] == "original"


def test_apply_params_does_not_mutate_original():
    wf = {"6": {"inputs": {"text": "original"}}}
    apply_params(wf, {"6.text": "changed"})
    assert wf["6"]["inputs"]["text"] == "original"


# ---------------------------------------------------------------------------
# execute_job retry / dead-letter logic
# ---------------------------------------------------------------------------

def _make_redis_mock(job_data: dict):
    r = MagicMock()
    r.get.return_value = json.dumps(job_data)
    return r


def test_execute_job_retries_on_failure():
    job = {
        "job_id": "test-job-1",
        "user_id": 1,
        "job_type": "image",
        "workflow": "t2i/zimage-t2i.api.json",
        "params": {},
        "callback_url": "http://callback",
        "status": "queued",
        "retry_count": 0,
        "error": None,
    }
    r = _make_redis_mock(job)

    with patch("workers.media_tasks.load_workflow", side_effect=FileNotFoundError("missing")):
        with pytest.raises(FileNotFoundError):
            execute_job(job, comfyui_base_url="http://comfyui", redis_client=r, callback_secret="s", max_retries=3)

    # Should re-push to queue (not dead-letter yet, retry_count was 0)
    push_calls = [c for c in r.rpush.call_args_list]
    queues = [c[0][0] for c in push_calls]
    assert "media:photo" in queues
    assert "media:dead" not in queues


def test_execute_job_dead_letters_after_max_retries():
    job = {
        "job_id": "test-job-2",
        "user_id": 2,
        "job_type": "image",
        "workflow": "t2i/zimage-t2i.api.json",
        "params": {},
        "callback_url": "http://callback",
        "status": "queued",
        "retry_count": 3,  # already exhausted
        "error": None,
    }
    r = _make_redis_mock(job)

    with patch("workers.media_tasks.load_workflow", side_effect=ComfyUIError("boom")):
        with pytest.raises(ComfyUIError):
            execute_job(job, comfyui_base_url="http://comfyui", redis_client=r, callback_secret="s", max_retries=3)

    push_calls = [c[0][0] for c in r.rpush.call_args_list]
    assert DEAD_QUEUE in push_calls
    assert "media:photo" not in push_calls


def test_execute_job_gateway_capability_posts_multipart_callback():
    """task #10：有 capability 的照片任務走 gateway，並維持 /internal/media_done 回推格式。"""
    job = {
        "job_id": "gw-job",
        "user_id": 1,
        "job_type": "image",
        "capability": "t2i",
        "gen_params": {"prompt": "a girl"},
        "images": {},
        "callback_url": "http://coolify/internal/media_done",
        "status": "queued",
        "retry_count": 0,
        "error": None,
    }
    r = _make_redis_mock(job)

    fake_post_response = MagicMock()
    fake_post_response.raise_for_status = lambda: None

    with patch(
        "shared.comfyui_gateway.generate_sync",
        return_value={
            "outputs": [
                {"url": "http://gw/outputs/out.jpg", "type": "image", "filename": "out.jpg"},
            ],
        },
    ) as mock_generate, \
         patch("shared.comfyui_gateway.download_output_sync", return_value=b"imgdata") as mock_download, \
         patch("httpx.post", return_value=fake_post_response) as mock_post:
        execute_job(
            job,
            comfyui_base_url="http://comfyui",
            redis_client=r,
            callback_secret="s",
            max_retries=3,
        )

    mock_generate.assert_called_once_with(
        "t2i",
        {"prompt": "a girl"},
        {},
        wait=True,
        timeout=600.0,
    )
    mock_download.assert_called_once_with("http://gw/outputs/out.jpg", timeout=120.0)
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["data"]["job_id"] == "gw-job"
    assert call_kwargs["files"]["file"][0] == "out.jpg"
    assert call_kwargs["headers"]["Authorization"] == "Bearer s"


def test_execute_job_video_retries_to_video_queue():
    job = {
        "job_id": "test-job-3",
        "user_id": 3,
        "job_type": "video",
        "workflow": "i2v/ltx23-10eros-q3ks-small.api.json",
        "params": {},
        "callback_url": "http://callback",
        "status": "queued",
        "retry_count": 0,
        "error": None,
    }
    r = _make_redis_mock(job)

    with patch("workers.media_tasks.load_workflow", side_effect=ComfyUIError("timeout")):
        with pytest.raises(ComfyUIError):
            execute_job(job, comfyui_base_url="http://comfyui", redis_client=r, callback_secret="s", max_retries=3)

    push_calls = [c[0][0] for c in r.rpush.call_args_list]
    assert VIDEO_QUEUE in push_calls
