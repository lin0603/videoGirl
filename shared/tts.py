"""Text-to-speech via BreezyVoice (the only TTS backend).

Flow (verified against the 4090 deployment):
  POST /v1/tts -> {job_id}  ->  poll GET /v1/jobs/{id} until status=completed
  -> GET /v1/audio/{id} (mp3) -> ffmpeg -> OGG/Opus bytes for Telegram sendVoice.

On any failure raise TTSError; callers (orchestrator/bot) fall back to TEXT
(NOT edge-tts). The "voice category" is a Voice: a reference-audio path on the
GPU box (+ its transcript) plus tempo. Configure per persona in the backend.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache

import httpx

from shared.config import get_settings
from shared.logging import get_logger

log = get_logger("tts")

_TERMINAL_OK = {"completed", "done", "succeeded", "finished"}
_TERMINAL_BAD = {"failed", "error", "cancelled", "canceled"}


class TTSError(RuntimeError):
    """Raised when speech cannot be produced (caller should fall back to text)."""


@dataclass(frozen=True)
class Voice:
    """A backend-configurable voice category (mirrors mentorAiClaude VoiceSchema).

    speaker_prompt_audio_path/text default to None -> the BreezyVoice server's
    built-in default reference voice.
    """

    slug: str = "default"
    speaker_prompt_audio_path: str | None = None
    speaker_prompt_text: str | None = None
    tempo: float = 1.0
    target_lufs: float = -16.0


DEFAULT_VOICE = Voice()


async def _mp3_to_ogg_opus(mp3: bytes, *, target_lufs: float) -> bytes:
    """Convert mp3 bytes -> OGG/Opus bytes (Telegram voice message format)."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0",
        "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
        "-c:a", "libopus", "-b:a", "48k", "-ar", "48000",
        "-f", "ogg", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(mp3)
    if proc.returncode != 0 or not out:
        raise TTSError(f"ffmpeg failed: {err.decode('utf-8', 'ignore')[:200]}")
    return out


class BreezyVoiceProvider:
    def __init__(self, base_url: str, token: str = "", *, timeout: float = 240, poll: float = 4.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.poll = poll

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def synthesize(self, text: str, voice: Voice = DEFAULT_VOICE) -> bytes:
        """Return OGG/Opus audio bytes for `text` in the given voice."""
        body: dict = {"text": text, "output_format": "mp3", "tempo": voice.tempo,
                      "target_lufs": voice.target_lufs}
        if voice.speaker_prompt_audio_path:
            body["speaker_prompt_audio_path"] = voice.speaker_prompt_audio_path
        if voice.speaker_prompt_text:
            body["speaker_prompt_text"] = voice.speaker_prompt_text

        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers) as client:
            try:
                r = await client.post(f"{self.base_url}/v1/tts", json=body)
                r.raise_for_status()
                job_id = r.json()["job_id"]
            except (httpx.HTTPError, KeyError, ValueError) as e:
                raise TTSError(f"submit failed: {e}") from e

            mp3 = await self._await_job(client, job_id)

        ogg = await _mp3_to_ogg_opus(mp3, target_lufs=voice.target_lufs)
        log.info("tts_ok", chars=len(text), voice=voice.slug, bytes=len(ogg))
        return ogg

    async def _await_job(self, client: httpx.AsyncClient, job_id: str) -> bytes:
        deadline = asyncio.get_event_loop().time() + self.timeout
        while True:
            try:
                j = (await client.get(f"{self.base_url}/v1/jobs/{job_id}")).json()
            except (httpx.HTTPError, ValueError) as e:
                raise TTSError(f"poll failed: {e}") from e
            status = (j.get("status") or "").lower()
            if status in _TERMINAL_OK:
                break
            if status in _TERMINAL_BAD:
                raise TTSError(f"job {job_id} {status}: {j.get('error', '')[:200]}")
            if asyncio.get_event_loop().time() > deadline:
                raise TTSError(f"job {job_id} timed out after {self.timeout}s")
            await asyncio.sleep(self.poll)

        try:
            audio = await client.get(f"{self.base_url}/v1/audio/{job_id}")
            audio.raise_for_status()
            return audio.content
        except httpx.HTTPError as e:
            raise TTSError(f"download failed: {e}") from e


@lru_cache(maxsize=1)
def get_tts() -> BreezyVoiceProvider:
    s = get_settings()
    return BreezyVoiceProvider(
        s.breezyvoice_base_url, s.breezyvoice_token,
        timeout=s.tts_timeout_secs, poll=s.tts_poll_secs,
    )


async def synthesize_ogg(text: str, voice: Voice = DEFAULT_VOICE) -> bytes:
    """Convenience: OGG/Opus bytes for a reply (raises TTSError on failure)."""
    return await get_tts().synthesize(text, voice)


async def _demo() -> None:
    import sys

    text = sys.argv[2] if len(sys.argv) > 2 else "你好呀,今天有沒有想我?"
    ogg = await synthesize_ogg(text)
    out = "/tmp/tts_demo.ogg"
    with open(out, "wb") as f:
        f.write(ogg)
    print(f"wrote {len(ogg)} bytes -> {out}")


if __name__ == "__main__":  # python -m shared.tts --demo "文字"
    import sys

    if "--demo" in sys.argv:
        asyncio.run(_demo())
    else:
        print('usage: python -m shared.tts --demo "要朗讀的文字"')
