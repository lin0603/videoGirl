from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class MiniAppAuthError(ValueError):
    pass


@dataclass(frozen=True)
class MiniAppUser:
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def validate_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int = 86400,
    now: int | None = None,
) -> MiniAppUser:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise MiniAppAuthError("missing initData hash")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(pairs.items())
    )
    expected_hash = hmac.new(
        _secret_key(bot_token),
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise MiniAppAuthError("invalid initData hash")

    auth_date_raw = pairs.get("auth_date")
    if not auth_date_raw:
        raise MiniAppAuthError("missing auth_date")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise MiniAppAuthError("invalid auth_date") from exc

    current = int(time.time()) if now is None else now
    if max_age_seconds > 0 and current - auth_date > max_age_seconds:
        raise MiniAppAuthError("expired initData")

    user_raw = pairs.get("user")
    if not user_raw:
        raise MiniAppAuthError("missing user")
    try:
        user_data = json.loads(user_raw)
        user_id = int(user_data["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MiniAppAuthError("invalid user") from exc

    return MiniAppUser(
        id=user_id,
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
        language_code=user_data.get("language_code"),
    )
