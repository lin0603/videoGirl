"""Tests for the FastAPI admin backend."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from admin.app import app
from admin.auth import sign_session


@pytest.fixture
def admin_client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def mock_repos():
    """Return empty catalogs so list pages render without a real DB."""
    with (
        patch("repositories.admin_repo.list_categories", new=AsyncMock(return_value=[])),
        patch("repositories.admin_repo.list_voices", new=AsyncMock(return_value=[])),
        patch("repositories.admin_repo.list_personas", new=AsyncMock(return_value=[])),
    ):
        yield


async def test_login_page(admin_client):
    r = await admin_client.get("/admin/login")
    assert r.status_code == 200
    assert "Admin 登入" in r.text


async def test_login_success(admin_client):
    r = await admin_client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert r.url.path == "/admin/"


async def test_login_failure(admin_client):
    r = await admin_client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong"},
    )
    assert r.status_code == 200
    assert "帳號或密碼錯誤" in r.text


async def test_protected_routes_redirect_when_anonymous(admin_client):
    r = await admin_client.get("/admin/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/admin/login"


async def test_dashboard_access_with_cookie(admin_client):
    admin_client.cookies.set("admin_session", sign_session("admin"))
    r = await admin_client.get("/admin/")
    assert r.status_code == 200
    assert "管理後台" in r.text


async def test_list_pages_render(admin_client):
    admin_client.cookies.set("admin_session", sign_session("admin"))
    for path, title in (
        ("/admin/categories", "語音分類"),
        ("/admin/voices", "語音"),
        ("/admin/personas", "人設"),
    ):
        r = await admin_client.get(path)
        assert r.status_code == 200, path
        assert title in r.text, path


async def test_logout_clears_cookie(admin_client):
    admin_client.cookies.set("admin_session", sign_session("admin"))
    r = await admin_client.get("/admin/logout", follow_redirects=False)
    assert r.status_code == 303
    assert "admin_session" not in r.cookies or r.cookies["admin_session"].value == ""
