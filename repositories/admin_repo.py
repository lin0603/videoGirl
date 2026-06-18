"""Async CRUD for admin-managed catalog entities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.models import Persona, Voice, VoiceCategory


# Voice categories


async def list_categories(session: AsyncSession, active_only: bool = False) -> list[VoiceCategory]:
    stmt = select(VoiceCategory).order_by(VoiceCategory.sort_order, VoiceCategory.name)
    if active_only:
        stmt = stmt.where(VoiceCategory.active == True)  # noqa: E712
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_category(session: AsyncSession, slug: str) -> VoiceCategory | None:
    return await session.get(VoiceCategory, slug)


async def create_category(session: AsyncSession, data: dict) -> VoiceCategory:
    cat = VoiceCategory(**data)
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat


async def update_category(session: AsyncSession, cat: VoiceCategory, data: dict) -> VoiceCategory:
    for key, value in data.items():
        setattr(cat, key, value)
    await session.commit()
    await session.refresh(cat)
    return cat


async def delete_category(session: AsyncSession, cat: VoiceCategory) -> None:
    await session.delete(cat)
    await session.commit()


# Voices


async def list_voices(session: AsyncSession, active_only: bool = False) -> list[Voice]:
    stmt = (
        select(Voice)
        .options(selectinload(Voice.category))
        .order_by(Voice.sort_order, Voice.name)
    )
    if active_only:
        stmt = stmt.where(Voice.active == True)  # noqa: E712
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_voice(session: AsyncSession, slug: str) -> Voice | None:
    return await session.get(Voice, slug)


async def create_voice(session: AsyncSession, data: dict) -> Voice:
    voice = Voice(**data)
    session.add(voice)
    await session.commit()
    await session.refresh(voice)
    return voice


async def update_voice(session: AsyncSession, voice: Voice, data: dict) -> Voice:
    for key, value in data.items():
        setattr(voice, key, value)
    await session.commit()
    await session.refresh(voice)
    return voice


async def delete_voice(session: AsyncSession, voice: Voice) -> None:
    await session.delete(voice)
    await session.commit()


# Personas


async def list_personas(session: AsyncSession, active_only: bool = False) -> list[Persona]:
    stmt = select(Persona).order_by(Persona.sort_order, Persona.name)
    if active_only:
        stmt = stmt.where(Persona.active == True)  # noqa: E712
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_persona(session: AsyncSession, slug: str) -> Persona | None:
    return await session.get(Persona, slug)


async def create_persona(session: AsyncSession, data: dict) -> Persona:
    persona = Persona(**data)
    session.add(persona)
    await session.commit()
    await session.refresh(persona)
    return persona


async def update_persona(session: AsyncSession, persona: Persona, data: dict) -> Persona:
    for key, value in data.items():
        setattr(persona, key, value)
    await session.commit()
    await session.refresh(persona)
    return persona


async def delete_persona(session: AsyncSession, persona: Persona) -> None:
    await session.delete(persona)
    await session.commit()
