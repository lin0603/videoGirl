from __future__ import annotations

import os
from pathlib import Path

from aiogram import Bot
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from miniapp.security import (
    MiniAppAuthError,
    MiniAppUser,
    _SESSION_TTL,
    create_session_token,
    decode_session_token,
    validate_init_data,
)
from shared.config import get_settings
from shared.db import AsyncSessionLocal
from shared.intimacy import IntimacyService
from shared.payments import StarsPaymentService, UnknownProductError
from shared.repositories.subscription_repo import EntitlementService
from shared.repositories.user_repo import UserRepository
from shared.wallet import WalletService

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

router = APIRouter()


class InitDataRequest(BaseModel):
    init_data: str


class InitDataResponse(BaseModel):
    ok: bool
    user_id: int
    username: str | None = None


class SessionResponse(BaseModel):
    token: str
    expires_in: int
    user_id: int


class InvoiceLinkRequest(BaseModel):
    product: str  # session-auth; no need to re-send init_data


class InvoiceLinkResponse(BaseModel):
    invoice_link: str
    payload: str
    amount_stars: int
    product: str


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


_bearer = HTTPBearer(auto_error=False)


def _auth(init_data: str) -> MiniAppUser:
    settings = get_settings()
    try:
        return validate_init_data(
            init_data,
            bot_token=settings.telegram_token,
            max_age_seconds=settings.mini_app_init_data_max_age_seconds,
        )
    except MiniAppAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> int:
    """FastAPI dependency: validates Bearer session token, returns user_id."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    try:
        return decode_session_token(
            credentials.credentials,
            secret_key=get_settings().admin_secret_key,
        )
    except MiniAppAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


async def _ensure_user(session: AsyncSession, user: MiniAppUser) -> None:
    await UserRepository(session).create_or_update(
        telegram_id=user.id,
        username=user.username,
        display_name=" ".join(
            part for part in [user.first_name, user.last_name] if part
        )
        or user.username,
    )


@router.get("/", include_in_schema=False)
async def mini_app_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.post("/api/telegram/validate-init-data")
async def validate_telegram_init_data(body: InitDataRequest) -> InitDataResponse:
    user = _auth(body.init_data)
    return InitDataResponse(ok=True, user_id=user.id, username=user.username)


@router.post("/api/auth/session")
async def create_session(
    body: InitDataRequest,
    session: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """
    Exchange Telegram initData for a short-lived session token.
    Front-end calls this once on app open, then uses the token for all subsequent requests.
    """
    user = _auth(body.init_data)
    await _ensure_user(session, user)
    settings = get_settings()
    token = create_session_token(user.id, secret_key=settings.admin_secret_key)
    return SessionResponse(token=token, expires_in=_SESSION_TTL, user_id=user.id)


@router.post("/api/payments/stars/invoice-link")
async def create_stars_invoice_link(
    body: InvoiceLinkRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> InvoiceLinkResponse:
    service = StarsPaymentService(session)
    bot = Bot(get_settings().telegram_token)
    try:
        tx = await service.create_invoice_link(
            bot=bot,
            user_id=user_id,
            product_slug=body.product,
        )
    except UnknownProductError as exc:
        raise HTTPException(status_code=404, detail="unknown product") from exc
    finally:
        await bot.session.close()

    return InvoiceLinkResponse(
        invoice_link=tx.invoice_link or "",
        payload=tx.payload,
        amount_stars=tx.amount_stars,
        product=tx.product,
    )


class UserStatusResponse(BaseModel):
    user_id: int
    display_name: str | None
    is_vip: bool
    balance: int
    intimacy_level: int
    intimacy_level_name: str
    intimacy_score: float
    streak_days: int
    active_persona_slug: str


class PersonaResponse(BaseModel):
    slug: str
    name: str
    personality: str


@router.get("/api/user/status")
async def get_user_status(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> UserStatusResponse:
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    entitlements = EntitlementService(session)
    is_vip = await entitlements.nsfw_allowed(user)
    balance = await WalletService(session).get_balance(user_id)
    status = await IntimacyService(session).get_status(user_id)
    from orchestrator.persona import DEFAULT_PERSONA
    persona_slug = getattr(user, "active_persona_slug", DEFAULT_PERSONA)

    return UserStatusResponse(
        user_id=user_id,
        display_name=user.display_name,
        is_vip=is_vip,
        balance=balance,
        intimacy_level=status.level,
        intimacy_level_name=status.level_name,
        intimacy_score=status.score,
        streak_days=status.streak,
        active_persona_slug=persona_slug,
    )


@router.get("/api/personas")
async def list_personas(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> list[PersonaResponse]:
    from orchestrator.persona import PERSONAS
    repo = UserRepository(session)
    await repo.get_by_telegram_id(user_id)  # auth gate
    return [
        PersonaResponse(slug=p.slug, name=p.name, personality=p.personality)
        for p in PERSONAS.values()
    ]


class SubscriptionStatusResponse(BaseModel):
    is_vip: bool
    expires_at: str | None  # ISO format or None


class GalleryItemResponse(BaseModel):
    type: str   # "gacha" or "unlock"
    key: str    # rarity+scene_key (gacha) or item_key (unlock)
    label: str
    created_at: str


class SwitchPersonaRequest(BaseModel):
    slug: str


@router.get("/api/subscription/status")
async def get_subscription_status(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> SubscriptionStatusResponse:
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    entitlements = EntitlementService(session)
    is_vip = await entitlements.nsfw_allowed(user)
    # Fetch subscription expiry.
    from sqlalchemy import select
    from shared.models import Subscription
    result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status == "active")
        .order_by(Subscription.current_period_end.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    expires_at = sub.current_period_end.isoformat() if sub else None
    return SubscriptionStatusResponse(is_vip=is_vip, expires_at=expires_at)


@router.get("/api/gallery")
async def get_gallery(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> list[GalleryItemResponse]:
    """Return user's gacha draws and unlocks, most recent first (up to 50 items)."""
    from sqlalchemy import select, union_all, literal
    from shared.models import GachaDraw, Unlock

    result_gacha = await session.execute(
        select(GachaDraw)
        .where(GachaDraw.user_id == user_id)
        .order_by(GachaDraw.drawn_at.desc())
        .limit(50)
    )
    result_unlock = await session.execute(
        select(Unlock)
        .where(Unlock.user_id == user_id)
        .order_by(Unlock.unlocked_at.desc())
        .limit(50)
    )

    items = []
    rarity_label = {"R": "✨ 普通", "SR": "💎 稀有", "SSR": "🌟 超稀有"}
    for draw in result_gacha.scalars():
        items.append(GalleryItemResponse(
            type="gacha",
            key=f"{draw.rarity}:{draw.scene_key}",
            label=f"{rarity_label.get(draw.rarity, draw.rarity)} — {draw.scene_key}",
            created_at=draw.drawn_at.isoformat(),
        ))
    for unlock in result_unlock.scalars():
        items.append(GalleryItemResponse(
            type="unlock",
            key=unlock.item_key,
            label=f"🔓 {unlock.item_key}",
            created_at=unlock.unlocked_at.isoformat(),
        ))

    items.sort(key=lambda x: x.created_at, reverse=True)
    return items[:50]


@router.post("/api/personas/switch")
async def switch_persona(
    body: SwitchPersonaRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    from orchestrator.persona import PERSONAS
    if body.slug not in PERSONAS:
        raise HTTPException(status_code=404, detail="unknown persona slug")
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    user.active_persona_slug = body.slug
    await session.flush()
    return {"ok": True, "slug": body.slug}


def register_mini_app(app: FastAPI) -> None:
    origins = [
        origin.strip()
        for origin in get_settings().mini_app_allowed_origins.split(",")
        if origin.strip()
    ] or ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Telegram-Init-Data"],
    )

    @app.middleware("http")
    async def mini_app_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' https://telegram.org; "
            "style-src 'self'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors https://web.telegram.org https://*.telegram.org;",
        )
        return response

    app.mount("/miniapp-static", StaticFiles(directory=STATIC_DIR), name="miniapp-static")
    app.include_router(router)
