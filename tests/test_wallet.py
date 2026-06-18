"""Tests for the atomic credit wallet."""

import pytest
import asyncio

from shared.repositories.user_repo import UserRepository
from shared.wallet import InsufficientCreditsError, WalletService


async def _create_test_user(session, telegram_id: int = 300):
    return await UserRepository(session).create_or_update(
        telegram_id=telegram_id,
        username="tester",
        display_name="Tester",
    )


@pytest.mark.asyncio
async def test_top_up_increases_balance(db_session):
    user = await _create_test_user(db_session)
    service = WalletService(db_session)

    wallet = await service.top_up(
        user.telegram_id, 100, reason="test_topup", reference="ref_1"
    )
    assert wallet.balance == 100
    assert await service.get_balance(user.telegram_id) == 100

    wallet = await service.top_up(
        user.telegram_id, 50, reason="test_topup", reference="ref_2"
    )
    assert wallet.balance == 150


@pytest.mark.asyncio
async def test_debit_decreases_balance(db_session):
    user = await _create_test_user(db_session)
    service = WalletService(db_session)

    await service.top_up(user.telegram_id, 100, reason="test_topup")
    wallet = await service.debit(user.telegram_id, 30, reason="image_gen")
    assert wallet.balance == 70


@pytest.mark.asyncio
async def test_debit_insufficient_fails(db_session):
    user = await _create_test_user(db_session)
    service = WalletService(db_session)

    with pytest.raises(InsufficientCreditsError):
        await service.debit(user.telegram_id, 10, reason="image_gen")


@pytest.mark.asyncio
async def test_concurrent_debits_never_go_negative(db_session):
    user = await _create_test_user(db_session)
    service = WalletService(db_session)
    await service.top_up(user.telegram_id, 10, reason="test_topup")

    async def attempt():
        try:
            await WalletService(db_session).debit(
                user.telegram_id, 10, reason="concurrent_debit"
            )
            return "ok"
        except InsufficientCreditsError:
            return "insufficient"

    results = await asyncio.gather(*[attempt() for _ in range(5)])
    ok_count = results.count("ok")
    assert ok_count == 1, f"expected exactly one successful debit, got {ok_count}"
    assert await service.get_balance(user.telegram_id) == 0


@pytest.mark.asyncio
async def test_ledger_records_entries(db_session):
    user = await _create_test_user(db_session)
    service = WalletService(db_session)

    await service.top_up(user.telegram_id, 100, reason="stars_topup", reference="chg_1")
    await service.debit(user.telegram_id, 25, reason="image_gen", reference="job_1")

    entries = await service.ledger(user.telegram_id)
    assert len(entries) == 2
    assert entries[0].delta == -25
    assert entries[1].delta == 100
