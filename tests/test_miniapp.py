import hashlib
import hmac
import json
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import text

from miniapp.security import validate_init_data


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


async def test_miniapp_creates_invoice_link(monkeypatch, db_engine) -> None:
    from admin.app import app
    import miniapp.app as miniapp_app

    class FakeBot:
        def __init__(self, token: str) -> None:
            self.token = token
            self.session = AsyncMock()
            self.session.close = AsyncMock()

        async def create_invoice_link(self, **kwargs):
            self.kwargs = kwargs
            return "https://t.me/invoice/mini"

    monkeypatch.setattr(miniapp_app, "Bot", FakeBot)
    init_data = make_init_data("test-token")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/payments/stars/invoice-link",
            json={"init_data": init_data, "product": "photo_pack"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["invoice_link"] == "https://t.me/invoice/mini"
    assert body["amount_stars"] == 25
