"""Scene template library for photo generation (task #11).

Templates provide consistent positive/negative prompt fragments for different
scenarios, keeping style and composition predictable across generations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SceneKey = Literal[
    "selfie",
    "outdoor_casual",
    "indoor_cozy",
    "beach",
    "bedroom_sfw",
    "bedroom_nsfw",
    "lingerie",
    "topless",
    "gift_birthday",
    "gift_anniversary",
]

_BASE_QUALITY = (
    "photorealistic, 8k uhd, RAW photo, masterpiece, best quality, "
    "sharp focus, perfect lighting, film grain"
)

_BASE_NEG = (
    "lowres, bad anatomy, bad hands, text, watermark, logo, blurry, "
    "worst quality, jpeg artifacts, deformed, ugly, censored"
)

_PERSON_BASE_SFW = (
    "beautiful young Taiwanese woman, 22 years old, "
    "flawless skin, natural makeup, dark brown hair"
)

_PERSON_BASE_NSFW = _PERSON_BASE_SFW + ", sensual"


@dataclass(frozen=True)
class SceneTemplate:
    key: str
    positive: str
    negative: str
    nsfw: bool = False


TEMPLATES: dict[str, SceneTemplate] = {
    "selfie": SceneTemplate(
        key="selfie",
        positive=(
            f"{_PERSON_BASE_SFW}, taking a selfie, close-up portrait, "
            "smile, casual outfit, soft bokeh background, {lora_trigger} {_BASE_QUALITY}"
        ).format(lora_trigger="{lora_trigger}", _BASE_QUALITY=_BASE_QUALITY),
        negative=_BASE_NEG,
    ),
    "outdoor_casual": SceneTemplate(
        key="outdoor_casual",
        positive=(
            f"{_PERSON_BASE_SFW}, outdoors, sunny day, casual streetwear, "
            "full body shot, city background, golden hour, {lora_trigger} {_BASE_QUALITY}"
        ).format(lora_trigger="{lora_trigger}", _BASE_QUALITY=_BASE_QUALITY),
        negative=_BASE_NEG,
    ),
    "indoor_cozy": SceneTemplate(
        key="indoor_cozy",
        positive=(
            f"{_PERSON_BASE_SFW}, indoors, cozy café or living room, "
            "warm light, casual comfortable outfit, {lora_trigger} {_BASE_QUALITY}"
        ).format(lora_trigger="{lora_trigger}", _BASE_QUALITY=_BASE_QUALITY),
        negative=_BASE_NEG,
    ),
    "beach": SceneTemplate(
        key="beach",
        positive=(
            f"{_PERSON_BASE_SFW}, beach, swimsuit, ocean background, "
            "sunny, sand, natural light, {lora_trigger} {_BASE_QUALITY}"
        ).format(lora_trigger="{lora_trigger}", _BASE_QUALITY=_BASE_QUALITY),
        negative=_BASE_NEG,
    ),
    "bedroom_sfw": SceneTemplate(
        key="bedroom_sfw",
        positive=(
            f"{_PERSON_BASE_SFW}, cozy bedroom, morning light, pajamas, "
            "natural relaxed pose, warm atmosphere, {lora_trigger} {_BASE_QUALITY}"
        ).format(lora_trigger="{lora_trigger}", _BASE_QUALITY=_BASE_QUALITY),
        negative=_BASE_NEG + ", nude, explicit",
    ),
    "bedroom_nsfw": SceneTemplate(
        key="bedroom_nsfw",
        positive=(
            f"{_PERSON_BASE_NSFW}, bedroom, dim warm light, seductive pose, "
            "partially undressed, nsfw, {lora_trigger} {_BASE_QUALITY}"
        ).format(lora_trigger="{lora_trigger}", _BASE_QUALITY=_BASE_QUALITY),
        negative=_BASE_NEG,
        nsfw=True,
    ),
    "lingerie": SceneTemplate(
        key="lingerie",
        positive=(
            f"{_PERSON_BASE_NSFW}, wearing lingerie, boudoir style, "
            "soft studio light, nsfw, {lora_trigger} {_BASE_QUALITY}"
        ).format(lora_trigger="{lora_trigger}", _BASE_QUALITY=_BASE_QUALITY),
        negative=_BASE_NEG,
        nsfw=True,
    ),
    "topless": SceneTemplate(
        key="topless",
        positive=(
            f"{_PERSON_BASE_NSFW}, topless, nude upper body, tasteful, "
            "soft light, nsfw, {lora_trigger} {_BASE_QUALITY}"
        ).format(lora_trigger="{lora_trigger}", _BASE_QUALITY=_BASE_QUALITY),
        negative=_BASE_NEG,
        nsfw=True,
    ),
    "gift_birthday": SceneTemplate(
        key="gift_birthday",
        positive=(
            "birthday cake with candles, colorful balloons, flowers, gift boxes, "
            "festive celebration, warm happy atmosphere, bokeh, "
            "photorealistic, 8k uhd, best quality"
        ),
        negative=_BASE_NEG,
    ),
    "gift_anniversary": SceneTemplate(
        key="gift_anniversary",
        positive=(
            "red roses bouquet, romantic candles, anniversary dinner table, "
            "love letter, bokeh, warm golden light, "
            "photorealistic, 8k uhd, best quality"
        ),
        negative=_BASE_NEG,
    ),
}


def get_template(key: str) -> SceneTemplate | None:
    return TEMPLATES.get(key)


def build_prompt(
    template_key: str,
    *,
    lora_trigger: str = "",
    extra: str = "",
    nsfw_ok: bool = False,
) -> tuple[str, str] | None:
    """
    Return (positive_prompt, negative_prompt) for a template.
    Returns None if the template requires NSFW but nsfw_ok=False.
    """
    tmpl = TEMPLATES.get(template_key)
    if tmpl is None:
        return None
    if tmpl.nsfw and not nsfw_ok:
        return None

    positive = tmpl.positive.replace("{lora_trigger}", lora_trigger).strip()
    if extra:
        positive = f"{positive}, {extra}"
    return positive, tmpl.negative
