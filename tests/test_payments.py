from aiogram.types import SuccessfulPayment
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from shared.payments import STARS_CURRENCY, STARS_PROVIDER_TOKEN, StarsPaymentService
from shared.repositories.user_repo import UserRepository


@pytest.fixture(autouse=True)
async def clean_payment_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE TABLE payment_transactions, users RESTART IDENTITY CASCADE")
        )


async def create_user(session: AsyncSession, telegram_id: int = 9001) -> None:
    await UserRepository(session).create_or_update(
        telegram_id=telegram_id,
        username="payer",
        display_name="Paying User",
    )


async def test_create_invoice_link_uses_telegram_stars(db_engine) -> None:
    bot = AsyncMock()
    bot.create_invoice_link = AsyncMock(return_value="https://t.me/invoice/test")

    async with AsyncSession(bind=db_engine) as session:
        await create_user(session)
        tx = await StarsPaymentService(session).create_invoice_link(
            bot=bot,
            user_id=9001,
            product_slug="photo_pack",
        )

    assert tx.invoice_link == "https://t.me/invoice/test"
    kwargs = bot.create_invoice_link.call_args.kwargs
    assert kwargs["currency"] == STARS_CURRENCY
    assert kwargs["provider_token"] == STARS_PROVIDER_TOKEN
    assert kwargs["prices"][0].amount == 25


async def test_successful_payment_delivery_is_idempotent(db_engine) -> None:
    async with AsyncSession(bind=db_engine) as session:
        await create_user(session)
        service = StarsPaymentService(session)
        tx, _ = await service.create_invoice_payload(
            user_id=9001,
            product_slug="photo_pack",
        )
        payment = SuccessfulPayment(
            currency=STARS_CURRENCY,
            total_amount=tx.amount_stars,
            invoice_payload=tx.payload,
            telegram_payment_charge_id="charge-1",
            provider_payment_charge_id="",
        )

        first_tx, first_delivered = await service.record_successful_payment(
            user_id=9001,
            payment=payment,
        )
        second_tx, second_delivered = await service.record_successful_payment(
            user_id=9001,
            payment=payment,
        )

    assert first_delivered is True
    assert second_delivered is False
    assert first_tx.id == second_tx.id
    assert first_tx.telegram_payment_charge_id == "charge-1"


async def test_validate_pre_checkout_marks_transaction(db_engine) -> None:
    async with AsyncSession(bind=db_engine) as session:
        await create_user(session)
        service = StarsPaymentService(session)
        tx, _ = await service.create_invoice_payload(
            user_id=9001,
            product_slug="photo_pack",
        )

        checked = await service.validate_pre_checkout(
            user_id=9001,
            payload=tx.payload,
            currency=STARS_CURRENCY,
            total_amount=tx.amount_stars,
        )

    assert checked.status == "pre_checkout"


async def test_refund_star_payment_marks_refunded(db_engine) -> None:
    bot = AsyncMock()
    bot.refund_star_payment = AsyncMock(return_value=True)

    async with AsyncSession(bind=db_engine) as session:
        await create_user(session)
        service = StarsPaymentService(session)
        tx, _ = await service.create_invoice_payload(
            user_id=9001,
            product_slug="photo_pack",
        )
        payment = SuccessfulPayment(
            currency=STARS_CURRENCY,
            total_amount=tx.amount_stars,
            invoice_payload=tx.payload,
            telegram_payment_charge_id="charge-refund",
            provider_payment_charge_id="",
        )
        await service.record_successful_payment(user_id=9001, payment=payment)

        refunded = await service.refund(bot=bot, charge_id="charge-refund")

    assert refunded.status == "refunded"
    bot.refund_star_payment.assert_awaited_once_with(
        user_id=9001,
        telegram_payment_charge_id="charge-refund",
    )
