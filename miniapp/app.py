from __future__ import annotations

import os
from pathlib import Path

from aiogram import Bot
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from miniapp.security import MiniAppAuthError, MiniAppUser, validate_init_data
from shared.config import get_settings
from shared.db import AsyncSessionLocal
from shared.payments import StarsPaymentService, UnknownProductError
from shared.repositories.user_repo import UserRepository

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

router = APIRouter()


class InitDataRequest(BaseModel):
    init_data: str


class InitDataResponse(BaseModel):
    ok: bool
    user_id: int
    username: str | None = None


class InvoiceLinkRequest(BaseModel):
    init_data: str
    product: str


class InvoiceLinkResponse(BaseModel):
    invoice_link: str
    payload: str
    amount_stars: int
    product: str


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


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


@router.post("/api/payments/stars/invoice-link")
async def create_stars_invoice_link(
    body: InvoiceLinkRequest,
    session: AsyncSession = Depends(get_db),
) -> InvoiceLinkResponse:
    user = _auth(body.init_data)
    await _ensure_user(session, user)
    service = StarsPaymentService(session)
    bot = Bot(get_settings().telegram_token)
    try:
        tx = await service.create_invoice_link(
            bot=bot,
            user_id=user.id,
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


def register_mini_app(app: FastAPI) -> None:
    origins = [
        origin.strip()
        for origin in os.getenv("mini_app_allowed_origins", "*").split(",")
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
