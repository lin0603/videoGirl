import hashlib
import hmac
import json
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import text

from miniapp.security import (
    MiniAppAuthError,
    create_session_token,
    decode_session_token,
    validate_init_data,
)


def make_init_data(bot_token: str, user_id: int = 7001, auth_date: int = 1_800_000_000) -> str:
    params = {
        "auth_date": str(auth_date),
        "query_id": "mini-query",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": "Mini",
                "last_name": "User",
                "username": "miniuser",
                "language_code": "zh-TW",
            },
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(params)


@pytest.fixture(autouse=True)
async def clean_miniapp_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE TABLE payment_transactions, users RESTART IDENTITY CASCADE")
        )


def test_validate_init_data_hmac() -> None:
    user = validate_init_data(
        make_init_data("123456:TEST"),
        bot_token="123456:TEST",
        now=1_800_000_010,
    )

    assert user.id == 7001
    assert user.username == "miniuser"


async def test_miniapp_root_serves_static_page() -> None:
    from admin.app import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "videoGirl" in response.text
    assert "Content-Security-Policy" in response.headers


# --- Session token unit tests ---

def test_session_token_roundtrip() -> None:
    token = create_session_token(12345, secret_key="secret")
    user_id = decode_session_token(token, secret_key="secret")
    assert user_id == 12345


def test_session_token_tampered_raises() -> None:
    token = create_session_token(12345, secret_key="secret")
    tampered = token[:-4] + "XXXX"
    with pytest.raises(MiniAppAuthError, match="invalid"):
        decode_session_token(tampered, secret_key="secret")


def test_session_token_expired_raises() -> None:
    token = create_session_token(12345, secret_key="secret")
    with pytest.raises(MiniAppAuthError, match="expired"):
        decode_session_token(token, secret_key="secret", max_age=-1)


def test_session_token_wrong_key_raises() -> None:
    token = create_session_token(12345, secret_key="secret")
    with pytest.raises(MiniAppAuthError):
        decode_session_token(token, secret_key="different-secret")


# --- /api/auth/session endpoint ---

async def test_create_session_returns_token() -> None:
    from admin.app import app

    init_data = make_init_data("test-token", auth_date=1_800_000_000)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/auth/session",
            json={"init_data": init_data},
        )

    assert response.status_code == 200
    body = response.json()
    assert "token" in body
    assert body["user_id"] == 7001
    assert body["expires_in"] == 3600


async def test_create_session_invalid_init_data_returns_401() -> None:
    from admin.app import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/auth/session",
            json={"init_data": "hash=badhash&auth_date=1800000000"},
        )

    assert response.status_code == 401


# --- /api/payments/stars/invoice-link with session token ---

async def test_miniapp_creates_invoice_link(monkeypatch, db_engine) -> None:
    from admin.app import app
    import miniapp.app as miniapp_app
    from shared.config import get_settings

    class FakeBot:
        def __init__(self, token: str) -> None:
            self.token = token
            self.session = AsyncMock()
            self.session.close = AsyncMock()

        async def create_invoice_link(self, **kwargs):
            self.kwargs = kwargs
            return "https://t.me/invoice/mini"

    monkeypatch.setattr(miniapp_app, "Bot", FakeBot)
    init_data = make_init_data("test-token", auth_date=1_800_000_000)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Exchange initData for session token (also creates user row)
        session_resp = await client.post(
            "/api/auth/session",
            json={"init_data": init_data},
        )
        assert session_resp.status_code == 200
        token = session_resp.json()["token"]

        response = await client.post(
            "/api/payments/stars/invoice-link",
            json={"product": "photo_pack"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["invoice_link"] == "https://t.me/invoice/mini"
    assert body["amount_stars"] == 25


async def test_invoice_link_no_token_returns_401(monkeypatch) -> None:
    from admin.app import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/payments/stars/invoice-link",
            json={"product": "photo_pack"},
        )

    assert response.status_code == 401


async def test_invoice_link_invalid_token_returns_401(monkeypatch) -> None:
    from admin.app import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/payments/stars/invoice-link",
            json={"product": "photo_pack"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )

    assert response.status_code == 401
