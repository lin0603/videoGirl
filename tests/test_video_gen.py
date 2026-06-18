"""Tests for task #14: I2V worker + video_gen service."""
from unittest.mock import AsyncMock, MagicMock, patch


# ---- video_gen intent detection ----

def test_is_video_request_zh() -> None:
    from shared.video_gen import is_video_request
    assert is_video_request("傳個影片給我")
    assert is_video_request("動起來")


def test_is_video_request_en() -> None:
    from shared.video_gen import is_video_request
    assert is_video_request("send me a video clip")
    assert is_video_request("show me a gif")


def test_is_not_video_request() -> None:
    from shared.video_gen import is_video_request
    assert not is_video_request("你好嗎")
    assert not is_video_request("傳一張照片給我")


# ---- request_video ----

async def test_request_video_no_callback_returns_none() -> None:
    from shared.video_gen import request_video
    with patch("shared.video_gen.get_settings") as ms:
        ms.return_value.media_callback_url = ""
        result = await request_video(1001, source_image_url="http://example.com/img.jpg")
    assert result is None


async def test_request_video_enqueues_job() -> None:
    from shared.video_gen import request_video
    mock_enqueue = AsyncMock(return_value="job-vid-001")
    with patch("shared.video_gen.get_settings") as ms, \
         patch("shared.video_gen.enqueue_video_job", mock_enqueue):
        ms.return_value.media_callback_url = "http://coolify/internal/media_done"
        job_id = await request_video(
            1001,
            source_image_url="http://example.com/img.jpg",
            nsfw=False,
        )
    assert job_id == "job-vid-001"
    call_kwargs = mock_enqueue.call_args.kwargs
    assert call_kwargs["user_id"] == 1001
    assert "i2v" in call_kwargs["workflow"]
    params = call_kwargs["params"]
    assert params["_source_image_url"] == "http://example.com/img.jpg"
    assert "_source_image_node" in params
    assert "89.text" in params


# ---- comfyui_runner upload_image ----

def test_upload_image_sends_correct_request() -> None:
    import httpx
    from workers.comfyui_runner import upload_image

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"name": "src_abc123.jpg"}

    def fake_post(url, **kwargs):
        captured.update(url=url, kwargs=kwargs)
        return FakeResponse()

    with patch("workers.comfyui_runner.httpx") as mhttpx:
        mhttpx.post.return_value = FakeResponse()
        name = upload_image("http://comfyui:8188", b"imgbytes", "myfile.jpg")

    assert name == "src_abc123.jpg"


# ---- media_tasks: source image pre-upload for I2V ----

def test_execute_job_uploads_source_image() -> None:
    """Worker fetches source image, uploads to ComfyUI, then uses returned filename."""
    # Patch the names as they appear in media_tasks module (direct imports).
    fake_outputs = {"8": {"images": [{"filename": "out.mp4", "subfolder": "", "type": "output"}]}}

    fake_img_response = MagicMock()
    fake_img_response.raise_for_status = lambda: None
    fake_img_response.content = b"imgdata"

    fake_post_response = MagicMock()
    fake_post_response.raise_for_status = lambda: None

    posted_params = {}

    def fake_apply(wf, params):
        posted_params.update(params)
        return wf

    with patch("workers.media_tasks.load_workflow", return_value={"97": {"class_type": "LoadImage", "inputs": {"image": "default.jpg"}}}), \
         patch("workers.media_tasks.apply_params", side_effect=fake_apply), \
         patch("workers.media_tasks.upload_image", return_value="uploaded_src.jpg"), \
         patch("workers.media_tasks.submit_prompt", return_value="prompt-001"), \
         patch("workers.media_tasks.wait_for_completion", return_value=fake_outputs), \
         patch("workers.media_tasks.download_output", return_value=(b"viddata", "out.mp4")), \
         patch("httpx.get", return_value=fake_img_response), \
         patch("httpx.post", return_value=fake_post_response):

        r = MagicMock()
        r.get = MagicMock(return_value=None)

        from workers.media_tasks import execute_job
        execute_job(
            {
                "job_id": "test-i2v-001",
                "job_type": "video",
                "workflow": "i2v/wan22-i2v-q4km.api.json",
                "params": {
                    "_source_image_url": "http://cdn.example.com/photo.jpg",
                    "_source_image_node": "97",
                    "89.text": "beautiful woman",
                },
                "callback_url": "http://coolify/internal/media_done",
            },
            comfyui_base_url="http://comfyui:8188",
            redis_client=r,
            callback_secret="secret",
        )

    assert "97.image" in posted_params, f"97.image not in {posted_params}"
    assert posted_params["97.image"] == "uploaded_src.jpg"
    assert "_source_image_url" not in posted_params
