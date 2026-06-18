import httpx
import pytest

import shared.tts as tts
from shared.tts import BreezyVoiceProvider, TTSError, Voice


class _Resp:
    def __init__(self, json_data=None, content=b"", status=200):
        self._json = json_data
        self.content = content
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _Client:
    """Scriptable fake httpx.AsyncClient."""

    def __init__(self, statuses, *, submit_raises=False, mp3=b"MP3"):
        self._statuses = list(statuses)
        self._submit_raises = submit_raises
        self._mp3 = mp3

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        if self._submit_raises:
            raise httpx.ConnectError("down")
        return _Resp({"job_id": "j1"})

    async def get(self, url):
        if "/v1/jobs/" in url:
            return _Resp({"status": self._statuses.pop(0)})
        if "/v1/audio/" in url:
            return _Resp(content=self._mp3)
        raise AssertionError(url)


@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch):
    async def fake_conv(mp3, *, target_lufs):
        return b"OGG:" + mp3

    monkeypatch.setattr(tts, "_mp3_to_ogg_opus", fake_conv)


def _provider():
    return BreezyVoiceProvider("http://x:7868", "", timeout=5, poll=0)


async def test_synthesize_polls_until_completed(monkeypatch):
    monkeypatch.setattr(tts.httpx, "AsyncClient", _Client(["running", "running", "completed"], mp3=b"M"))
    out = await _provider().synthesize("你好", Voice(slug="xiaorou"))
    assert out == b"OGG:M"


async def test_job_failure_raises(monkeypatch):
    monkeypatch.setattr(tts.httpx, "AsyncClient", _Client(["running", "failed"]))
    with pytest.raises(TTSError):
        await _provider().synthesize("你好")


async def test_submit_error_raises(monkeypatch):
    monkeypatch.setattr(tts.httpx, "AsyncClient", _Client(["completed"], submit_raises=True))
    with pytest.raises(TTSError):
        await _provider().synthesize("你好")


async def test_voice_params_sent(monkeypatch):
    captured = {}

    client = _Client(["completed"])
    orig_post = client.post

    async def spy_post(url, json=None):
        captured["body"] = json
        return await orig_post(url, json=json)

    client.post = spy_post
    monkeypatch.setattr(tts.httpx, "AsyncClient", client)
    await _provider().synthesize(
        "嗨", Voice(slug="v", speaker_prompt_audio_path="/p.wav", tempo=1.2)
    )
    assert captured["body"]["speaker_prompt_audio_path"] == "/p.wav"
    assert captured["body"]["tempo"] == 1.2
    assert captured["body"]["output_format"] == "mp3"
