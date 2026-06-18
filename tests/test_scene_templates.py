"""Tests for task #11: scene templates + LoRA routing."""
from shared.scene_templates import build_prompt, get_template


def test_sfw_template_returns_prompt() -> None:
    result = build_prompt("selfie", nsfw_ok=False)
    assert result is not None
    positive, negative = result
    assert "woman" in positive.lower()
    assert "nsfw" not in positive.lower()


def test_nsfw_template_blocked_without_opt_in() -> None:
    result = build_prompt("topless", nsfw_ok=False)
    assert result is None


def test_nsfw_template_allowed_with_opt_in() -> None:
    result = build_prompt("topless", nsfw_ok=True)
    assert result is not None
    positive, _ = result
    assert "nsfw" in positive.lower()


def test_lora_trigger_injected() -> None:
    result = build_prompt("selfie", lora_trigger="XiaorouV2", nsfw_ok=False)
    assert result is not None
    positive, _ = result
    assert "XiaorouV2" in positive


def test_extra_context_appended() -> None:
    result = build_prompt("selfie", extra="birthday party", nsfw_ok=False)
    assert result is not None
    positive, _ = result
    assert "birthday party" in positive


def test_unknown_template_returns_none() -> None:
    result = build_prompt("nonexistent_scene", nsfw_ok=True)
    assert result is None


def test_get_template_returns_dataclass() -> None:
    tmpl = get_template("beach")
    assert tmpl is not None
    assert tmpl.nsfw is False


def test_gift_birthday_template_has_cake() -> None:
    result = build_prompt("gift_birthday", nsfw_ok=False)
    assert result is not None
    positive, _ = result
    assert "birthday" in positive.lower() or "cake" in positive.lower()


def test_all_sfw_templates_available() -> None:
    sfw_keys = ["selfie", "outdoor_casual", "indoor_cozy", "beach", "bedroom_sfw"]
    for key in sfw_keys:
        r = build_prompt(key, nsfw_ok=False)
        assert r is not None, f"Template '{key}' should work without NSFW"
