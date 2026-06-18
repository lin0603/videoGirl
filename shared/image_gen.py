"""
Image generation service — enqueues ComfyUI photo jobs for a user.

Uses the GPU queue (task #8) so photo delivery is async:
  1. Bot detects photo intent → calls request_photo()
  2. Worker picks up the job, runs ComfyUI, POSTs result to callback
  3. Callback endpoint delivers the image via sendPhoto

Task #11 addition: persona-specific LoRA routing + scene templates.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

from shared.config import get_settings
from shared.safety import check_image_prompt
from workers.queue_client import enqueue_image_job

_PHOTO_INTENT_RE = re.compile(
    r"(傳照片|寄照片|照片|自拍|selfie|selfies|看你|你的照片|傳一張|給我看|秀一下"
    r"|秀照片|讓我看看|拍一張|想看|拍個照|拍張照|show me|photo|pic)",
    re.IGNORECASE,
)

# Default prompts for the ZImage base workflow (no LoRA).
_SFW_PROMPT = (
    "photorealistic portrait photo of a beautiful young Taiwanese woman, "
    "natural smile, casual stylish outfit, indoor modern setting, "
    "professional lighting, sharp focus, high quality, 1girl, solo"
)
_NSFW_PROMPT = (
    "photorealistic intimate portrait of a beautiful young Taiwanese woman, "
    "seductive expression, bedroom, soft natural lighting, high quality, "
    "1girl, solo, nsfw, topless, TaiwanDollLikeness"
)

# Default workflow paths.
_WORKFLOW_ZIMAGE = "t2i/zimage-t2i.api.json"
_WORKFLOW_SDXL_LORA = "t2i/sdxl-lora-t2i.api.json"


@dataclass
class PersonaImageConfig:
    """Resolved image config for a persona."""
    workflow: str
    lora_name: str
    lora_strength: float
    lora_trigger: str  # e.g. "XiaorouV2" inserted into positive prompts


def _default_config() -> PersonaImageConfig:
    return PersonaImageConfig(
        workflow=_WORKFLOW_ZIMAGE,
        lora_name="",
        lora_strength=0.8,
        lora_trigger="",
    )


def persona_image_config(persona_slug: str | None) -> PersonaImageConfig:
    """
    Look up image config from the in-memory persona registry.
    Falls back to defaults if persona has no LoRA configured.
    """
    if not persona_slug:
        return _default_config()

    try:
        from orchestrator.persona import get_persona
        persona = get_persona(persona_slug)
        if not persona:
            return _default_config()
        # Persona dataclass has optional lora_name / lora_strength / image_workflow.
        lora_name = getattr(persona, "lora_name", "") or ""
        lora_strength = getattr(persona, "lora_strength", 0.8) or 0.8
        image_workflow = getattr(persona, "image_workflow", "") or ""
        lora_trigger = getattr(persona, "lora_trigger", "") or ""

        workflow = image_workflow if image_workflow else (
            _WORKFLOW_SDXL_LORA if lora_name else _WORKFLOW_ZIMAGE
        )
        return PersonaImageConfig(
            workflow=workflow,
            lora_name=lora_name,
            lora_strength=lora_strength,
            lora_trigger=lora_trigger,
        )
    except Exception:
        return _default_config()


def _build_lora_params(cfg: PersonaImageConfig, positive: str, negative: str, seed: int) -> dict:
    """Build workflow params for the SDXL+LoRA workflow."""
    return {
        "2.lora_name": cfg.lora_name,
        "2.strength_model": cfg.lora_strength,
        "2.strength_clip": cfg.lora_strength,
        "3.text": positive,
        "4.text": negative,
        "6.seed": seed,
    }


def _build_zimage_params(positive: str, seed: int) -> dict:
    """Build workflow params for the default ZImage workflow."""
    return {
        "4.prompt": positive,
        "6.seed": seed,
    }


def is_photo_request(text: str) -> bool:
    return bool(_PHOTO_INTENT_RE.search(text))


async def request_photo(
    user_id: int,
    *,
    nsfw: bool = False,
    extra_context: str = "",
    scene: str | None = None,
    persona_slug: str | None = None,
) -> str | None:
    """
    Enqueue a photo-generation job.

    If `scene` is given and persona has a LoRA, uses scene templates + SDXL workflow.
    Otherwise falls back to the ZImage default workflow.

    Returns job_id if queued, None if media_callback_url is not configured.
    """
    settings = get_settings()
    if not settings.media_callback_url:
        return None

    cfg = persona_image_config(persona_slug)
    seed = random.randint(1, 2**31 - 1)

    # Try scene template path when we have a scene key or a LoRA.
    if scene or cfg.lora_name:
        from shared.scene_templates import build_prompt
        key = scene or ("topless" if nsfw else "selfie")
        result = build_prompt(key, lora_trigger=cfg.lora_trigger, extra=extra_context, nsfw_ok=nsfw)
        if result:
            positive, negative = result
            if not check_image_prompt(positive, user_id=user_id).allowed:
                return None
            if cfg.lora_name:
                params = _build_lora_params(cfg, positive, negative, seed)
                workflow = cfg.workflow
            else:
                params = _build_zimage_params(positive, seed)
                workflow = _WORKFLOW_ZIMAGE
            return await enqueue_image_job(
                user_id=user_id,
                workflow=workflow,
                params=params,
                callback_url=settings.media_callback_url,
            )

    # Default ZImage path.
    base = _NSFW_PROMPT if nsfw else _SFW_PROMPT
    prompt = f"{base}, {extra_context}".rstrip(", ") if extra_context else base
    if not check_image_prompt(prompt, user_id=user_id).allowed:
        return None

    return await enqueue_image_job(
        user_id=user_id,
        workflow=_WORKFLOW_ZIMAGE,
        params={
            "4.prompt": prompt,
            "6.seed": seed,
        },
        callback_url=settings.media_callback_url,
    )
