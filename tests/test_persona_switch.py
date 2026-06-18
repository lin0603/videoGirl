"""Tests for task #26: multi-persona switching."""
from shared.repositories.user_repo import UserRepository


async def _make_user(session, uid: int):
    return await UserRepository(session).create_or_update(
        telegram_id=uid, username="switchtest", display_name="SwitchTest"
    )


def test_persona_registry_has_multiple() -> None:
    from orchestrator.persona import PERSONAS
    assert len(PERSONAS) >= 2
    for slug, p in PERSONAS.items():
        assert p.slug == slug
        assert p.name
        assert p.personality


def test_get_persona_returns_default() -> None:
    from orchestrator.persona import DEFAULT_PERSONA, PERSONAS, get_persona
    p = get_persona(None)
    assert p.slug == DEFAULT_PERSONA
    assert p == PERSONAS[DEFAULT_PERSONA]


def test_get_persona_by_slug() -> None:
    from orchestrator.persona import PERSONAS, get_persona
    for slug in PERSONAS:
        assert get_persona(slug).slug == slug


def test_get_persona_unknown_slug_raises() -> None:
    from orchestrator.persona import get_persona
    import pytest
    with pytest.raises(KeyError):
        get_persona("nonexistent_slug_xyz")


async def test_user_default_persona_is_set(db_session) -> None:
    from orchestrator.persona import DEFAULT_PERSONA
    user = await _make_user(db_session, 9001)
    assert user.active_persona_slug == DEFAULT_PERSONA


async def test_switch_persona_persists(db_session) -> None:
    from orchestrator.persona import PERSONAS
    user = await _make_user(db_session, 9002)

    # Pick a persona that is not the default
    from orchestrator.persona import DEFAULT_PERSONA
    other_slug = next(s for s in PERSONAS if s != DEFAULT_PERSONA)

    user.active_persona_slug = other_slug
    await db_session.flush()

    # Reload from DB
    refreshed = await UserRepository(db_session).get_by_telegram_id(9002)
    assert refreshed is not None
    assert refreshed.active_persona_slug == other_slug
