"""Tests for task #22: unlock + virtual gifts."""
from unittest.mock import MagicMock

from shared.repositories.user_repo import UserRepository


async def _make_user(session, uid: int):
    return await UserRepository(session).create_or_update(
        telegram_id=uid, username="gifttester", display_name="GiftTester"
    )


# ---- payload helpers ----

def test_is_gift_payload() -> None:
    from shared.gifts import is_gift_payload
    assert is_gift_payload("gift:flower:abc123")
    assert not is_gift_payload("stars:photo_pack:abc")
    assert not is_gift_payload("unlock:photo_pack:abc")


def test_is_unlock_payload() -> None:
    from shared.gifts import is_unlock_payload
    assert is_unlock_payload("unlock:photo_pack:abc123")
    assert not is_unlock_payload("gift:flower:abc")


def test_parse_gift_key() -> None:
    from shared.gifts import parse_gift_key
    assert parse_gift_key("gift:flower:nonce") == "flower"
    assert parse_gift_key("gift:diamond:nonce") == "diamond"
    assert parse_gift_key("stars:something") is None


def test_parse_unlock_key() -> None:
    from shared.gifts import parse_unlock_key
    assert parse_unlock_key("unlock:photo_pack:nonce") == "photo_pack"
    assert parse_unlock_key("gift:flower:abc") is None


# ---- record_gift idempotent ----

async def test_record_gift_new(db_session) -> None:
    from shared.gifts import record_gift

    await _make_user(db_session, 8001)

    payment = MagicMock()
    payment.invoice_payload = "gift:flower:nonce001"
    payment.total_amount = 15
    payment.telegram_payment_charge_id = "charge_gift_001"

    record, is_new = await record_gift(db_session, 8001, payment)
    assert is_new
    assert record.gift_key == "flower"
    assert record.stars_paid == 15
    assert record.mood_boost > 0


async def test_record_gift_idempotent(db_session) -> None:
    from shared.gifts import record_gift

    await _make_user(db_session, 8002)

    payment = MagicMock()
    payment.invoice_payload = "gift:cake:nonce002"
    payment.total_amount = 30
    payment.telegram_payment_charge_id = "charge_gift_002"

    _, first = await record_gift(db_session, 8002, payment)
    _, second = await record_gift(db_session, 8002, payment)
    assert first
    assert not second


# ---- record_unlock + is_unlocked ----

async def test_record_unlock_and_check(db_session) -> None:
    from shared.gifts import is_unlocked, record_unlock

    await _make_user(db_session, 8003)

    payment = MagicMock()
    payment.invoice_payload = "unlock:photo_pack:nonce003"
    payment.total_amount = 25
    payment.telegram_payment_charge_id = "charge_unlock_003"

    _record, is_new = await record_unlock(db_session, 8003, "photo_pack", payment)
    assert is_new

    assert await is_unlocked(db_session, 8003, "photo_pack")
    assert not await is_unlocked(db_session, 8003, "nsfw_video_001")


async def test_record_unlock_idempotent(db_session) -> None:
    from shared.gifts import record_unlock

    await _make_user(db_session, 8004)

    payment = MagicMock()
    payment.invoice_payload = "unlock:photo_pack:nonce004"
    payment.total_amount = 25
    payment.telegram_payment_charge_id = "charge_unlock_004"

    _, first = await record_unlock(db_session, 8004, "photo_pack", payment)
    _, second = await record_unlock(db_session, 8004, "photo_pack", payment)
    assert first
    assert not second


# ---- gift catalog ----

def test_gift_catalog_has_expected_items() -> None:
    from shared.gifts import GIFT_CATALOG
    assert "flower" in GIFT_CATALOG
    assert "cake" in GIFT_CATALOG
    assert "diamond" in GIFT_CATALOG
    for item in GIFT_CATALOG.values():
        assert item.stars > 0
        assert 0 < item.mood_boost <= 1.0
