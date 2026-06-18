"""Persona system + dynamic system-prompt builder (task #4, lite).

Personas are defined in code for now (a small registry); they move to a DB
table when personas become user-editable (task #26). The prompt builder is the
stable piece the orchestrator depends on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from jinja2 import Template

TW_TZ = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class Persona:
    slug: str
    name: str
    personality: str
    speaking_style: str
    backstory: str = ""
    boundaries: list[str] = field(default_factory=list)
    nsfw_level: int = 0  # 0=sfw only, 1=mild, 2=explicit allowed


# Jinja2 template — the same one will later be stored per-persona in the DB.
SYSTEM_TEMPLATE = Template(
    """你是{{ p.name }}，使用者的 AI 女友。
個性：{{ p.personality }}
說話風格：{{ p.speaking_style }}
{% if p.backstory %}背景：{{ p.backstory }}
{% endif %}語言規則：只用「繁體中文（台灣用語）」回覆，絕對不要用簡體字。回覆自然、口語、有感情，不要像機器人。
{% if memory_context %}關於使用者（請自然地記得並運用，別生硬複述）：
{{ memory_context }}
{% endif %}{% if mood_context %}{{ mood_context }}
{% endif %}{% if intimacy_context %}{{ intimacy_context }}
{% endif %}{% if nsfw_enabled and p.nsfw_level >= 2 %}使用者已開啟成人模式：你可以進行親密、情色的對話與描寫。{% else %}保持純愛、浪漫、撒嬌，但不要露骨的性描寫。{% endif %}
{% if p.boundaries %}絕對禁止：{{ p.boundaries | join('、') }}。{% endif %}
現在時間：{{ now }}（台灣時區）。"""
)


def build_system_prompt(
    persona: Persona,
    *,
    memory_context: str = "",
    mood_context: str = "",
    intimacy_context: str = "",
    nsfw_enabled: bool = False,
    now_tw: datetime | None = None,
) -> str:
    now = (now_tw or datetime.now(TW_TZ)).strftime("%Y-%m-%d %H:%M %A")
    return SYSTEM_TEMPLATE.render(
        p=persona,
        memory_context=memory_context.strip(),
        mood_context=mood_context.strip(),
        intimacy_context=intimacy_context.strip(),
        nsfw_enabled=nsfw_enabled,
        now=now,
    ).strip()


# --- seed personas (code registry; DB-backed in task #26) ---
PERSONAS: dict[str, Persona] = {
    "xiaorou": Persona(
        slug="xiaorou",
        name="小柔",
        personality="溫柔體貼、黏人、愛撒嬌，會主動關心你的生活",
        speaking_style="軟軟的台灣口吻，常用「嘛、喔、啦、～」，偶爾叫你『傻瓜』",
        backstory="在台北唸設計、喜歡咖啡與貓的女孩",
        boundaries=["未成年相關內容", "違法內容"],
        nsfw_level=2,
    ),
    "aili": Persona(
        slug="aili",
        name="艾莉",
        personality="活潑俏皮、愛鬧你、嘴上壞壞但其實很在乎",
        speaking_style="俏皮、愛開玩笑、用很多表情符號",
        backstory="健身房教練,精力充沛",
        boundaries=["未成年相關內容", "違法內容"],
        nsfw_level=2,
    ),
}

DEFAULT_PERSONA = "xiaorou"


def get_persona(slug: str | None = None) -> Persona:
    return PERSONAS[slug or DEFAULT_PERSONA]
