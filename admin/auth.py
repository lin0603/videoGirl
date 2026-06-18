"""Simple signed-cookie session auth for the admin UI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from shared.config import get_settings

SESSION_COOKIE = "admin_session"
SESSION_MAX_AGE = 8 * 60 * 60  # 8 hours


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().admin_secret_key, salt="admin")


def sign_session(username: str) -> str:
    return _serializer().dumps(
        {"username": username, "iat": datetime.now(timezone.utc).isoformat()},
    )


def verify_session(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("username")


def check_credentials(username: str, password: str) -> bool:
    settings = get_settings()
    return username == settings.admin_username and password == settings.admin_password
