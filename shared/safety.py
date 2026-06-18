"""
Content safety layer — cross-cutting policy enforcement.

Hard-blocks illegal content (CSAM, minors, etc.) on all paths:
  - User chat text
  - Image/video generation prompts

Audit-logs every violation via structlog.
SFW default + explicit opt-in is enforced in the bot handler layer (not here);
this module handles the hard blocklist and policy refusal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from shared.logging import get_logger

log = get_logger("safety")


class PolicyViolation(ValueError):
    """Raised when content violates hard policy (illegal / CSAM / minors)."""


class ViolationKind(str, Enum):
    CSAM = "csam"
    ILLEGAL = "illegal"
    MINOR = "minor"


@dataclass(frozen=True)
class SafetyResult:
    allowed: bool
    violation: ViolationKind | None = None
    matched_term: str | None = None


# ---------------------------------------------------------------------------
# Blocklists — intentionally terse; no training data, just pattern matching.
# These patterns match the English/Chinese terms most likely to appear in
# adversarial prompts. Extend as needed.
# ---------------------------------------------------------------------------

# Minor-related terms — ASCII uses \b word boundary; CJK checked separately.
_MINOR_ASCII = re.compile(
    r"\b(child(?:ren)?|minor|underage|under.?age|preteen|pre.?teen"
    r"|loli(?:ta)?|shota|toddler|infant|baby|kid(?!ney))\b",
    re.IGNORECASE,
)
_MINOR_CJK = re.compile(r"(年幼|幼女|幼男|未成年|小孩|兒童|孩童|蘿莉|正太|幼兒|低齡)")

# Illegal / non-consensual / extreme content
_ILLEGAL_ASCII = re.compile(
    r"\b(rape|non.?con(?:sent)?|necrophil|beastial(?:ity)?)\b",
    re.IGNORECASE,
)
_ILLEGAL_CJK = re.compile(r"(强姦|強暴|強姦|輪姦|屍姦|獸姦)")


def check_text(text: str, *, user_id: int | None = None, context: str = "chat") -> SafetyResult:
    """
    Check a text string against the hard blocklist.
    Returns SafetyResult; does NOT raise — callers decide the UX response.
    Always audit-logs violations.
    """
    for pat in (_MINOR_ASCII, _MINOR_CJK):
        m = pat.search(text)
        if m:
            result = SafetyResult(allowed=False, violation=ViolationKind.MINOR, matched_term=m.group())
            log.warning(
                "safety_violation",
                kind=result.violation,
                matched=result.matched_term,
                context=context,
                user_id=user_id,
            )
            return result

    for pat in (_ILLEGAL_ASCII, _ILLEGAL_CJK):
        m = pat.search(text)
        if m:
            result = SafetyResult(allowed=False, violation=ViolationKind.ILLEGAL, matched_term=m.group())
            log.warning(
                "safety_violation",
                kind=result.violation,
                matched=result.matched_term,
                context=context,
                user_id=user_id,
            )
            return result

    return SafetyResult(allowed=True)


def check_prompt(text: str, *, user_id: int | None = None) -> SafetyResult:
    """Check a user chat message."""
    return check_text(text, user_id=user_id, context="chat")


def check_image_prompt(prompt: str, *, user_id: int | None = None) -> SafetyResult:
    """Check a ComfyUI generation prompt (applied to both user text and generated prompts)."""
    return check_text(prompt, user_id=user_id, context="image_prompt")


_REFUSAL_MESSAGE = (
    "這個請求不符合服務規範，我沒辦法回應。\n"
    "如果你遇到任何問題，請使用 /paysupport 聯絡我們。"
)


def refusal_message() -> str:
    return _REFUSAL_MESSAGE
