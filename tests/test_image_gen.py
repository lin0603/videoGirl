"""Tests for the image generation service (task #10)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from shared.image_gen import _NSFW_PROMPT, _SFW_PROMPT, is_photo_request, request_photo


def test_is_photo_request_detects_zh_keywords():
    assert is_photo_request("傳照片給我看")
    assert is_photo_request("你可以自拍嗎")
    assert is_photo_request("讓我看看你")
    assert is_photo_request("秀照片")


def test_is_photo_request_detects_en_keywords():
    assert is_photo_request("send me a selfie")
    assert is_photo_request("show me a photo")


def test_is_photo_request_false_for_unrelated():
    assert not is_photo_request("你好啊")
    assert not is_photo_request("今天天氣怎麼樣")
    assert not is_photo_request("/start")


@pytest.mark.asyncio
async def test_request_photo_returns_none_when_no_callback_url():
    with patch("shared.image_gen.get_settings") as mock_settings:
        mock_settings.return_value.media_callback_url = ""
        result = await request_photo(123, nsfw=False)
    assert result is None


@pytest.mark.asyncio
async def test_request_photo_enqueues_sfw_t2i_job():
    with patch("shared.image_gen.get_settings") as mock_settings, \
         patch("shared.image_gen.enqueue_image_job", new=AsyncMock(return_value="job-001")) as mock_enqueue:
        mock_settings.return_value.media_callback_url = "http://coolify/internal/media_done"

        job_id = await request_photo(456, nsfw=False)

    assert job_id == "job-001"
    call_kwargs = mock_enqueue.call_args.kwargs
    assert call_kwargs["user_id"] == 456
    # task #10：照片改走 gateway capability，不再是 node-keyed params。
    assert call_kwargs["capability"] == "t2i"
    prompt = call_kwargs["gen_params"]["prompt"]
    assert "nsfw" not in prompt.lower()
    assert "topless" not in prompt.lower()
    assert call_kwargs["gen_params"]["seed"] > 0
    assert call_kwargs["images"] == {}


@pytest.mark.asyncio
async def test_request_photo_enqueues_nsfw_t2i_job():
    with patch("shared.image_gen.get_settings") as mock_settings, \
         patch("shared.image_gen.enqueue_image_job", new=AsyncMock(return_value="job-002")) as mock_enqueue:
        mock_settings.return_value.media_callback_url = "http://coolify/internal/media_done"

        job_id = await request_photo(789, nsfw=True)

    assert job_id == "job-002"
    assert mock_enqueue.call_args.kwargs["capability"] == "t2i"
    prompt = mock_enqueue.call_args.kwargs["gen_params"]["prompt"]
    assert "nsfw" in prompt.lower()


@pytest.mark.asyncio
async def test_request_photo_with_source_image_uses_washout():
    with patch("shared.image_gen.get_settings") as mock_settings, \
         patch("shared.image_gen.enqueue_image_job", new=AsyncMock(return_value="job-w")) as mock_enqueue:
        mock_settings.return_value.media_callback_url = "http://coolify/internal/media_done"

        job_id = await request_photo(
            999,
            nsfw=True,
            source_image_url="http://cdn.example.com/source.jpg",
        )

    assert job_id == "job-w"
    call_kwargs = mock_enqueue.call_args.kwargs
    assert call_kwargs["capability"] == "washout"
    assert "prompt" in call_kwargs["gen_params"]
    assert "negative" in call_kwargs["gen_params"]
    assert call_kwargs["images"] == {"source": "http://cdn.example.com/source.jpg"}


@pytest.mark.asyncio
async def test_request_photo_includes_random_seed():
    seeds = set()
    with patch("shared.image_gen.get_settings") as mock_settings, \
         patch("shared.image_gen.enqueue_image_job", new=AsyncMock(return_value="job-x")) as mock_enqueue:
        mock_settings.return_value.media_callback_url = "http://callback"
        for _ in range(5):
            await request_photo(1, nsfw=False)
            seeds.add(mock_enqueue.call_args.kwargs["gen_params"]["seed"])
    # All 5 jobs should have different seeds (extremely unlikely to collide)
    assert len(seeds) > 1
