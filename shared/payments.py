from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.types import LabeledPrice, SuccessfulPayment
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import PaymentTransaction

STARS_CURRENCY = "XTR"
STARS_PROVIDER_TOKEN = ""


@dataclass(frozen=True)
class StarsProduct:
    slug: str
    title: str
    description: str
    amount_stars: int


PRODUCTS: dict[str, StarsProduct] = {
    "photo_pack": StarsProduct(
        slug="photo_pack",
        title="寫真解鎖包",
        description="解鎖一組 AI 女友數位寫真內容。",
        amount_stars=25,
    ),
    "vip_day": StarsProduct(
        slug="vip_day",
        title="VIP 一日體驗",
        description="解鎖 24 小時 VIP 數位服務體驗。",
        amount_stars=99,
    ),
}


class UnknownProductError(ValueError):
    pass


class PaymentValidationError(ValueError):
    pass


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_invoice_transaction(
        self,
        *,
        user_id: int,
        product: StarsProduct,
        invoice_link: str | None = None,
    ) -> PaymentTransaction:
        tx = PaymentTransaction(
            user_id=user_id,
            payload=f"stars:{product.slug}:{secrets.token_urlsafe(18)}",
            product=product.slug,
            amount_stars=product.amount_stars,
            status="invoice_created",
            invoice_link=invoice_link,
        )
        self.session.add(tx)
        await self.session.commit()
        await self.session.refresh(tx)
        return tx

    async def get_by_payload(self, payload: str) -> PaymentTransaction | None:
        result = await self.session.execute(
            select(PaymentTransaction).where(PaymentTransaction.payload == payload)
        )
        return result.scalar_one_or_none()

    async def get_by_charge_id(self, charge_id: str) -> PaymentTransaction | None:
        result = await self.session.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.telegram_payment_charge_id == charge_id
            )
        )
        return result.scalar_one_or_none()

    async def mark_paid_and_delivered(
        self,
        *,
        transaction: PaymentTransaction,
        payment: SuccessfulPayment,
    ) -> tuple[PaymentTransaction, bool]:
        existing = await self.get_by_charge_id(payment.telegram_payment_charge_id)
        if existing is not None:
            return existing, False

        now = datetime.utcnow()
        transaction.status = "delivered"
        transaction.telegram_payment_charge_id = payment.telegram_payment_charge_id
        transaction.provider_payment_charge_id = payment.provider_payment_charge_id
        transaction.delivered_at = now
        transaction.updated_at = now
        try:
            await self.session.commit()
        except IntegrityError:
            # Concurrent re-delivery of the same charge_id raced past the read
            # above; the unique constraint caught it -> treat as already done.
            await self.session.rollback()
            existing = await self.get_by_charge_id(payment.telegram_payment_charge_id)
            if existing is not None:
                return existing, False
            raise
        await self.session.refresh(transaction)
        return transaction, True

    async def mark_refunded(self, transaction: PaymentTransaction) -> PaymentTransaction:
        now = datetime.utcnow()
        transaction.status = "refunded"
        transaction.refunded_at = now
        transaction.updated_at = now
        await self.session.commit()
        await self.session.refresh(transaction)
        return transaction


class StarsPaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = PaymentRepository(session)

    def get_product(self, slug: str) -> StarsProduct:
        product = PRODUCTS.get(slug)
        if product is None:
            raise UnknownProductError(f"unknown Stars product: {slug}")
        return product

    async def create_invoice_link(
        self,
        *,
        bot: Bot,
        user_id: int,
        product_slug: str,
    ) -> PaymentTransaction:
        product = self.get_product(product_slug)
        tx = await self.repo.create_invoice_transaction(user_id=user_id, product=product)
        invoice_link = await bot.create_invoice_link(
            title=product.title,
            description=product.description,
            payload=tx.payload,
            currency=STARS_CURRENCY,
            provider_token=STARS_PROVIDER_TOKEN,
            prices=[LabeledPrice(label=product.title, amount=product.amount_stars)],
        )
        tx.invoice_link = invoice_link
        await self.repo.session.commit()
        await self.repo.session.refresh(tx)
        return tx

    async def create_invoice_payload(
        self,
        *,
        user_id: int,
        product_slug: str,
    ) -> tuple[PaymentTransaction, StarsProduct]:
        product = self.get_product(product_slug)
        tx = await self.repo.create_invoice_transaction(user_id=user_id, product=product)
        return tx, product

    async def validate_pre_checkout(
        self,
        *,
        user_id: int,
        payload: str,
        currency: str,
        total_amount: int,
    ) -> PaymentTransaction:
        tx = await self.repo.get_by_payload(payload)
        if tx is None:
            raise PaymentValidationError("找不到付款請求，請重新開立發票。")
        if tx.user_id != user_id:
            raise PaymentValidationError("付款使用者與發票不符。")
        if currency != STARS_CURRENCY:
            raise PaymentValidationError("付款幣別不正確。")
        if tx.amount_stars != total_amount:
            raise PaymentValidationError("付款金額不正確。")
        if tx.status not in {"invoice_created", "pre_checkout"}:
            raise PaymentValidationError("此發票狀態無法付款。")

        tx.status = "pre_checkout"
        tx.updated_at = datetime.utcnow()
        await self.repo.session.commit()
        await self.repo.session.refresh(tx)
        return tx

    async def record_successful_payment(
        self,
        *,
        user_id: int,
        payment: SuccessfulPayment,
    ) -> tuple[PaymentTransaction, bool]:
        tx = await self.repo.get_by_payload(payment.invoice_payload)
        if tx is None:
            raise PaymentValidationError("找不到付款紀錄。")
        if tx.user_id != user_id:
            raise PaymentValidationError("付款使用者與紀錄不符。")
        if payment.currency != STARS_CURRENCY:
            raise PaymentValidationError("付款幣別不正確。")
        if payment.total_amount != tx.amount_stars:
            raise PaymentValidationError("付款金額不正確。")
        return await self.repo.mark_paid_and_delivered(transaction=tx, payment=payment)

    async def refund(
        self,
        *,
        bot: Bot,
        charge_id: str,
    ) -> PaymentTransaction:
        tx = await self.repo.get_by_charge_id(charge_id)
        if tx is None:
            raise PaymentValidationError("找不到可退款的付款紀錄。")
        if tx.status == "refunded":
            raise PaymentValidationError("這筆付款已經退款過了。")
        await bot.refund_star_payment(
            user_id=tx.user_id,
            telegram_payment_charge_id=charge_id,
        )
        return await self.repo.mark_refunded(tx)
