"""Tests for task #30: Mini App backend API endpoints."""
import hashlib
import hmac
import json
from unittest.mock import MagicMock
from urllib.parse import urlencode

import httpx
import pytest
from sqlalchemy import text


def _make_init_data(
    bot_token: str = "test-token",
    user_id: int = 6001,
    auth_date: int = 1_800_000_000,
) -> str:
    params = {
        "auth_date": str(auth_date),
        "query_id": "api-test-query",
        "user": json.dumps(
            {"id": user_id, "first_name": "Api", "last_name": "Test", "username": "apitest"},
            separators=(",", ":"),
        ),
    }
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(params)


@pytest.fixture(autouse=True)
async def clean_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE gacha_draws, unlocks, gift_records,"
                " payment_transactions, users RESTART IDENTITY CASCADE"
            )
        )


async def _session_token(user_id: int = 6001) -> str:
    from admin.app import app
    init_data = _make_init_data(user_id=user_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post("/api/auth/session", json={"init_data": init_data})
    assert r.status_code == 200, f"auth failed: {r.text}"
    return r.json()["token"]


# ---- /api/user/status ----

async def test_user_status_returns_data() -> None:
    from admin.app import app
    token = await _session_token(6001)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.get("/api/user/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user_id"] == 6001
    assert "balance" in data
    assert "intimacy_level" in data
    assert "active_persona_slug" in data


async def test_user_status_no_token_returns_401() -> None:
    from admin.app import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.get("/api/user/status")
    assert r.status_code == 401


# ---- /api/subscription/status ----

async def test_subscription_status_not_vip() -> None:
    from admin.app import app
    token = await _session_token(6002)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.get(
            "/api/subscription/status", headers={"Authorization": f"Bearer {token}"}
        )
    assert r.status_code == 200
    data = r.json()
    assert data["is_vip"] is False
    assert data["expires_at"] is None


# ---- /api/gallery ----

async def test_gallery_empty_initially() -> None:
    from admin.app import app
    token = await _session_token(6003)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.get("/api/gallery", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == []


async def test_gallery_shows_gacha_draws(db_engine) -> None:
    from admin.app import app
    from shared.db import AsyncSessionLocal
    from shared.gacha import record_draw

    token = await _session_token(6004)
    async with AsyncSessionLocal() as session:
        await record_draw(session, 6004, "SR", "lingerie")
        await record_draw(session, 6004, "R", "selfie")
        await session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.get("/api/gallery", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert all(i["type"] == "gacha" for i in items)


async def test_gallery_shows_unlocks(db_engine) -> None:
    from admin.app import app
    from shared.db import AsyncSessionLocal
    from shared.gifts import record_unlock

    token = await _session_token(6005)

    payment = MagicMock()
    payment.invoice_payload = "unlock:photo_pack:xyz123"
    payment.total_amount = 25
    payment.telegram_payment_charge_id = "charge_gal_test_001"

    async with AsyncSessionLocal() as session:
        await record_unlock(session, 6005, "photo_pack", payment)
        await session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.get("/api/gallery", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["type"] == "unlock"
    assert items[0]["key"] == "photo_pack"


# ---- /api/personas ----

async def test_personas_list_returns_all() -> None:
    from admin.app import app
    from orchestrator.persona import PERSONAS

    token = await _session_token(6006)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.get("/api/personas", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    slugs = {p["slug"] for p in r.json()}
    assert slugs == set(PERSONAS.keys())


# ---- /api/personas/switch ----

async def test_switch_persona_valid() -> None:
    from admin.app import app
    from orchestrator.persona import PERSONAS, DEFAULT_PERSONA

    token = await _session_token(6007)
    other = next(s for s in PERSONAS if s != DEFAULT_PERSONA)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/personas/switch",
            json={"slug": other},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    assert r.json()["slug"] == other


async def test_switch_persona_invalid_returns_404() -> None:
    from admin.app import app
    token = await _session_token(6008)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r = await client.post(
            "/api/personas/switch",
            json={"slug": "nonexistent_xyz"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 404
