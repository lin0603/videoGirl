"""Tests for Telegram Stars VIP subscriptions and entitlements."""

from datetime import datetime, timedelta, timezone

import pytest
from aiogram.types import SuccessfulPayment, User

from shared.models import Subscription
from shared.repositories.subscription_repo import (
    EntitlementService,
    SubscriptionRepository,
)
from shared.repositories.user_repo import UserRepository
from shared.subscriptions import (
    VIP_PAYLOAD_PREFIX,
    handle_successful_payment,
    is_vip_payload,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user(telegram_id: int = 42) -> User:
    return User(
        telegram_id=telegram_id,
        username="tester",
        display_name="Tester",
        locale="zh-TW",
    )


async def _create_test_user(session, telegram_id: int = 42):
    return await UserRepository(session).create_or_update(
        telegram_id=telegram_id,
        username="tester",
        display_name="Tester",
    )


@pytest.mark.asyncio
async def test_is_vip_payload():
    assert is_vip_payload(f"{VIP_PAYLOAD_PREFIX}abc123")
    assert not is_vip_payload("stars:photo_pack:abc123")


@pytest.mark.asyncio
async def test_create_subscription_grants_vip(db_session):
    user = await _create_test_user(db_session)
    repo = SubscriptionRepository(db_session)

    period_end = _utc_now() + timedelta(days=30)
    sub = await repo.create_or_extend(
        user_id=user.telegram_id,
        current_period_end=period_end,
        telegram_payment_charge_id="charge_1",
    )

    assert sub.status == "active"
    assert await EntitlementService(db_session).is_vip(user.telegram_id) is True


@pytest.mark.asyncio
async def test_expired_subscription_revokes_vip(db_session):
    user = await _create_test_user(db_session)
    repo = SubscriptionRepository(db_session)

    period_end = _utc_now() - timedelta(days=1)
    sub = await repo.create_or_extend(
        user_id=user.telegram_id,
        current_period_end=period_end,
        telegram_payment_charge_id="charge_2",
    )

    grace_started, expired = await repo.process_expirations()
    assert grace_started == 1
    assert expired == 0

    # Refresh to see grace status
    await db_session.refresh(sub)
    assert sub.status == "grace"

    # Still VIP during grace period
    assert await EntitlementService(db_session).is_vip(user.telegram_id) is True

    # Simulate grace period passing
    sub.grace_period_end = _utc_now() - timedelta(seconds=1)
    await db_session.commit()

    grace_started, expired = await repo.process_expirations()
    assert expired == 1
    assert await EntitlementService(db_session).is_vip(user.telegram_id) is False


@pytest.mark.asyncio
async def test_cancel_subscription_keeps_vip_until_period_end(db_session):
    user = await _create_test_user(db_session)
    repo = SubscriptionRepository(db_session)

    period_end = _utc_now() + timedelta(days=10)
    await repo.create_or_extend(
        user_id=user.telegram_id,
        current_period_end=period_end,
        telegram_payment_charge_id="charge_3",
    )
    cancelled = await repo.cancel(user.telegram_id)

    assert cancelled.status == "cancelled"
    assert await EntitlementService(db_session).is_vip(user.telegram_id) is True


@pytest.mark.asyncio
async def test_renew_extend_subscription(db_session):
    user = await _create_test_user(db_session)
    repo = SubscriptionRepository(db_session)

    first_end = _utc_now() + timedelta(days=10)
    await repo.create_or_extend(
        user_id=user.telegram_id,
        current_period_end=first_end,
        telegram_payment_charge_id="charge_4",
    )

    new_end = _utc_now() + timedelta(days=40)
    sub = await repo.create_or_extend(
        user_id=user.telegram_id,
        current_period_end=new_end,
        telegram_payment_charge_id="charge_5",
    )

    assert sub.status == "active"
    assert sub.current_period_end == new_end


@pytest.mark.asyncio
async def test_handle_successful_payment_creates_subscription(db_session):
    user = await _create_test_user(db_session)
    period_end = _utc_now() + timedelta(days=30)
    payment = SuccessfulPayment(
        currency="XTR",
        total_amount=199,
        invoice_payload=f"{VIP_PAYLOAD_PREFIX}token",
        telegram_payment_charge_id="charge_6",
        provider_payment_charge_id="provider_6",
        subscription_expiration_date=int(period_end.timestamp()),
    )

    _, is_new = await handle_successful_payment(
        db_session, user.telegram_id, payment
    )

    assert is_new is True
    assert await EntitlementService(db_session).is_vip(user.telegram_id) is True


@pytest.mark.asyncio
async def test_nsfw_requires_vip_and_opt_in(db_session):
    user = await _create_test_user(db_session)
    user.age_verified_at = _utc_now()
    user.nsfw_opt_in = True
    await db_session.commit()

    service = EntitlementService(db_session)
    assert await service.nsfw_allowed(user) is False

    await SubscriptionRepository(db_session).create_or_extend(
        user_id=user.telegram_id,
        current_period_end=_utc_now() + timedelta(days=30),
        telegram_payment_charge_id="charge_7",
    )

    assert await service.nsfw_allowed(user) is True
