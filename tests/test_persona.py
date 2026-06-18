from orchestrator.persona import build_system_prompt, get_persona


def test_prompt_contains_persona_identity():
    p = get_persona("xiaorou")
    prompt = build_system_prompt(p)
    assert p.name in prompt
    assert "繁體中文" in prompt  # language rule always present
    assert "簡體" in prompt  # explicit "no simplified" instruction


def test_nsfw_flag_changes_prompt():
    p = get_persona("xiaorou")  # nsfw_level=2
    sfw = build_system_prompt(p, nsfw_enabled=False)
    nsfw = build_system_prompt(p, nsfw_enabled=True)
    assert sfw != nsfw
    assert "成人模式" in nsfw
    assert "成人模式" not in sfw


def test_memory_context_injected():
    p = get_persona("xiaorou")
    without = build_system_prompt(p)
    with_mem = build_system_prompt(p, memory_context="使用者叫阿明,喜歡貓")
    assert "阿明" in with_mem
    assert "阿明" not in without
