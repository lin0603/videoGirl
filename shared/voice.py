"""Text-to-speech service inspired by mentorAiClaude's TTS pipeline.

Providers:
- breezevoice: zero-shot voice clone on GPU box (job-based).
- edge-tts: local/Azure fallback, no GPU required.
- existing: reuse an existing audio file/URL.

Output is always converted to Telegram voice format (Opus in OGG).
"""

from __future__ import annotations

import asyncio
import io
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from shared.config import get_settings
from shared.logging import get_logger

log = get_logger("voice")

VoiceProvider = Literal["breezevoice", "edge-tts", "existing"]

FALLBACK_VOICE = "zh-TW-HsiaoChenNeural"


@dataclass
class VoiceConfig:
    provider: VoiceProvider = "breezevoice"
    speed: float = 1.0
    reference_audio_url: str | None = None
    reference_audio_path: str | None = None
    reference_transcript: str | None = None
    fallback_voice: str = FALLBACK_VOICE


class VoiceError(RuntimeError):
    """Raised when TTS cannot produce audio."""


def tts_clean_text(t: str) -> str:
    """Clean text for TTS: symbols to spoken words, remove bullets, etc."""
    s = (t or "")
    # 角色扮演的動作/神情描述放在括號或星號內，不應被唸出來。
    # 例：（臉頰瞬間泛起紅暈，眼神閃爍著羞澀與期待）、(順手拉過你的手) 等。
    s = re.sub(r"（[^（）]*）", "", s)      # 全形括號
    s = re.sub(r"\([^()]*\)", "", s)        # 半形括號
    s = re.sub(r"【[^【】]*】", "", s)      # 全形方括號
    s = re.sub(r"\*[^*\n]+\*", "", s)       # *動作* markdown
    # 移除殘留的純表情符號（避免 TTS 亂唸），保留中英數與標點。
    s = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️❤]", "", s)
    # 清掉因刪除而產生的重複/開頭標點。
    s = re.sub(r"([，。！？～、])\1+", r"\1", s)
    s = re.sub(r"^[\s，。！？～、~]+", "", s)
    # Math / punctuation to spoken Chinese
    s = s.replace("＝", " 等於 ").replace("=", " 等於 ")
    s = s.replace("×", " 乘以 ")
    s = s.replace("÷", " 除以 ")
    s = s.replace("＋", " 加 ")
    s = re.sub(r"[-−–﹣－]", " 減 ", s)
    s = re.sub(r"[—―‧•▪◦·]+", "，", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Keep only if there is at least one speakable character
    if re.search(r"[一-鿿぀-ヿA-Za-z0-9ㄅ-ㄩ]", s):
        return s
    return ""


def _run_ffmpeg(input_path: str, output_path: str) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a",
        "libopus",
        "-b:a",
        "24k",
        "-ar",
        "24000",
        "-ac",
        "1",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise VoiceError(f"ffmpeg failed: {exc.stderr}") from exc
    except FileNotFoundError as exc:
        raise VoiceError("ffmpeg not found; install ffmpeg") from exc


def _to_voice_ogg(input_path: str) -> bytes:
    """Convert any audio file to Telegram voice OGG/Opus."""
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        output_path = tmp.name
    try:
        _run_ffmpeg(input_path, output_path)
        return Path(output_path).read_bytes()
    finally:
        Path(output_path).unlink(missing_ok=True)


def _silence_ogg(duration_sec: float = 1.2) -> bytes:
    """Generate a silent OGG for un-speakable content."""
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        output_path = tmp.name
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono",
                "-t",
                str(duration_sec),
                "-c:a",
                "libopus",
                "-b:a",
                "24k",
                output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return Path(output_path).read_bytes()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise VoiceError(f"ffmpeg silence failed: {exc}") from exc
    finally:
        Path(output_path).unlink(missing_ok=True)


async def _synthesize_edge_tts(text: str, config: VoiceConfig) -> bytes:
    """Use edge-tts Python package to produce mp3, then convert to ogg/opus."""
    try:
        import edge_tts
    except ImportError as exc:
        raise VoiceError("edge-tts not installed; run uv add edge-tts") from exc

    voice_name = config.fallback_voice or FALLBACK_VOICE
    speakable = tts_clean_text(text)
    if not speakable:
        log.warning("voice_no_speakable_content", text_preview=text[:60])
        return _silence_ogg()

    communicate = edge_tts.Communicate(speakable, voice_name)
    if abs(config.speed - 1.0) > 0.001:
        # edge-tts supports rate like +20% or -20%
        rate_pct = int((config.speed - 1.0) * 100)
        communicate = edge_tts.Communicate(
            speakable, voice_name, rate=f"{rate_pct:+d}%"
        )

    mp3_buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_buffer.write(chunk["data"])

    mp3_bytes = mp3_buffer.getvalue()
    if not mp3_bytes:
        raise VoiceError("edge-tts produced empty audio")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(mp3_bytes)
        mp3_path = tmp.name
    try:
        return _to_voice_ogg(mp3_path)
    finally:
        Path(mp3_path).unlink(missing_ok=True)


async def _synthesize_existing(config: VoiceConfig) -> bytes:
    if not config.reference_audio_url:
        raise VoiceError("existing voice requires reference_audio_url")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(config.reference_audio_url)
        if r.status_code != 200:
            raise VoiceError(f"download failed {r.status_code}")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(r.content)
            input_path = tmp.name
        try:
            return _to_voice_ogg(input_path)
        finally:
            Path(input_path).unlink(missing_ok=True)


async def _synthesize_breezyvoice(text: str, config: VoiceConfig) -> bytes:
    """Call BreezyVoice /v1/tts, poll job, download and convert."""
    settings = get_settings()
    base = str(settings.breezyvoice_base_url or "").rstrip("/")
    if not base:
        raise VoiceError("breezyvoice_base_url not configured")
    token = getattr(settings, "breezyvoice_token", "") or ""
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"

    clean_text = tts_clean_text(text) or text
    body: dict = {
        "text": clean_text,
        "output_format": "mp3",
    }
    if config.reference_audio_path:
        body["speaker_prompt_audio_path"] = config.reference_audio_path
        if config.reference_transcript:
            body["speaker_prompt_text"] = config.reference_transcript
    if abs(config.speed - 1.0) > 0.001:
        body["tempo"] = min(2.0, max(0.5, config.speed))

    async with httpx.AsyncClient(timeout=60) as client:
        submit = await client.post(
            f"{base}/v1/tts", json=body, headers=headers
        )
        # /v1/tts returns 202 Accepted with the job descriptor.
        if submit.status_code >= 300:
            raise VoiceError(
                f"breezyvoice submit {submit.status_code}: {submit.text[:200]}"
            )
        job_id = submit.json().get("job_id")
        if not job_id:
            raise VoiceError(f"breezyvoice: no job_id in {submit.text[:200]}")

        deadline = asyncio.get_event_loop().time() + 15 * 60
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(4)
            status_r = await client.get(f"{base}/v1/jobs/{job_id}", headers=headers)
            if status_r.status_code != 200:
                continue
            data = status_r.json()
            status = str(data.get("status", "")).lower()
            if status in ("completed", "done", "succeeded"):
                break
            if status in ("failed", "error"):
                raise VoiceError(f"breezyvoice job failed: {data}")
        else:
            raise VoiceError("breezyvoice timeout")

        dl = await client.get(f"{base}/v1/audio/{job_id}?format=mp3", headers=headers)
        if dl.status_code != 200:
            raise VoiceError(f"breezyvoice download {dl.status_code}")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(dl.content)
            mp3_path = tmp.name
        try:
            return _to_voice_ogg(mp3_path)
        finally:
            Path(mp3_path).unlink(missing_ok=True)


async def synthesize(text: str, config: VoiceConfig | None = None) -> bytes:
    """Generate a Telegram voice OGG from text."""
    cfg = config or VoiceConfig()
    log.info(
        "voice_synthesize",
        provider=cfg.provider,
        speed=cfg.speed,
        text_len=len(text),
    )

    if cfg.provider == "existing":
        return await _synthesize_existing(cfg)
    if cfg.provider == "breezevoice":
        return await _synthesize_breezyvoice(text, cfg)
    if cfg.provider == "edge-tts":
        return await _synthesize_edge_tts(text, cfg)
    raise VoiceError(f"unknown voice provider {cfg.provider}")


def voice_config_from_user(user) -> VoiceConfig:
    """Build VoiceConfig from a User ORM object."""
    return VoiceConfig(
        provider=user.voice_provider or "breezevoice",  # type: ignore[arg-type]
        speed=max(0.5, min(2.0, user.voice_speed or 1.0)),
        reference_audio_url=user.voice_reference_audio_url,
        reference_audio_path=user.voice_reference_audio_path,
    )
