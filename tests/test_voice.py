import pytest

import shared.voice as voice
from shared.voice import VoiceConfig, VoiceError, synthesize, tts_clean_text


class _Resp:
    def __init__(self, *, status=200, json_data=None, content=b"", text=""):
        self.status_code = status
        self._json = json_data
        self.content = content
        self.text = text

    def json(self):
        return self._json


class _Client:
    def __init__(self, *, submit_status=202, statuses=("completed",), audio=b"MP3"):
        self._submit_status = submit_status
        self._statuses = list(statuses)
        self._audio = audio

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        return _Resp(status=self._submit_status, json_data={"job_id": "j1"}, text="submitted")

    async def get(self, url, headers=None):
        if "/v1/jobs/" in url:
            return _Resp(json_data={"status": self._statuses.pop(0)})
        if "/v1/audio/" in url:
            return _Resp(content=self._audio)
        raise AssertionError(url)


@pytest.fixture(autouse=True)
def _stub_ffmpeg(monkeypatch):
    monkeypatch.setattr(voice, "_to_voice_ogg", lambda path: b"OGGDATA")


def test_default_provider_is_breezevoice():
    assert VoiceConfig().provider == "breezevoice"


async def test_breezevoice_accepts_202_and_polls(monkeypatch):
    monkeypatch.setattr(voice.httpx, "AsyncClient", _Client(submit_status=202, statuses=["running", "completed"]))
    out = await synthesize("你好呀", VoiceConfig(provider="breezevoice"))
    assert out == b"OGGDATA"


async def test_breezevoice_submit_error_raises(monkeypatch):
    monkeypatch.setattr(voice.httpx, "AsyncClient", _Client(submit_status=500))
    with pytest.raises(VoiceError):
        await synthesize("你好", VoiceConfig(provider="breezevoice"))


async def test_breezevoice_job_failed_raises(monkeypatch):
    monkeypatch.setattr(voice.httpx, "AsyncClient", _Client(statuses=["failed"]))
    with pytest.raises(VoiceError):
        await synthesize("你好", VoiceConfig(provider="breezevoice"))


def test_tts_clean_text_speaks_symbols():
    assert "等於" in tts_clean_text("1+1=2")
