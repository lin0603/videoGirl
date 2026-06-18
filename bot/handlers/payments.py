from aiogram import Bot, Router, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger
from shared.payments import (
    PRODUCTS,
    STARS_CURRENCY,
    STARS_PROVIDER_TOKEN,
    PaymentValidationError,
    StarsPaymentService,
    UnknownProductError,
)

logger = get_logger("bot.payments")


def get_router() -> Router:
    router = Router()

    @router.message(Command("products"))
    async def cmd_products(message: types.Message) -> None:
        lines = [
            f"・<code>{product.slug}</code> — {product.title}（{product.amount_stars} Stars）"
            for product in PRODUCTS.values()
        ]
        await message.answer(
            "可購買的數位商品：\n"
            + "\n".join(lines)
            + "\n\n用 /buy <商品代碼> 開立 Telegram Stars 發票。"
        )

    @router.message(Command("buy"))
    async def cmd_buy(message: types.Message, session: AsyncSession) -> None:
        parts = (message.text or "").split(maxsplit=1)
        product_slug = parts[1].strip() if len(parts) > 1 else "photo_pack"

        service = StarsPaymentService(session)
        try:
            tx, product = await service.create_invoice_payload(
                user_id=message.from_user.id,
                product_slug=product_slug,
            )
        except UnknownProductError:
            await message.answer("找不到這個商品。請用 /products 查看可購買項目。")
            return

        await message.answer_invoice(
            title=product.title,
            description=product.description,
            payload=tx.payload,
            currency=STARS_CURRENCY,
            provider_token=STARS_PROVIDER_TOKEN,
            prices=[types.LabeledPrice(label=product.title, amount=product.amount_stars)],
        )

    @router.pre_checkout_query()
    async def on_pre_checkout(
        query: types.PreCheckoutQuery,
        session: AsyncSession,
    ) -> None:
        service = StarsPaymentService(session)
        try:
            await service.validate_pre_checkout(
                user_id=query.from_user.id,
                payload=query.invoice_payload,
                currency=query.currency,
                total_amount=query.total_amount,
            )
        except PaymentValidationError as exc:
            logger.warning(
                "stars_pre_checkout_rejected",
                telegram_id=query.from_user.id,
                payload=query.invoice_payload,
                reason=str(exc),
            )
            await query.answer(ok=False, error_message=str(exc))
            return

        await query.answer(ok=True)

    @router.message(lambda message: message.successful_payment is not None)
    async def on_successful_payment(
        message: types.Message,
        session: AsyncSession,
    ) -> None:
        service = StarsPaymentService(session)
        try:
            tx, delivered = await service.record_successful_payment(
                user_id=message.from_user.id,
                payment=message.successful_payment,
            )
        except PaymentValidationError as exc:
            logger.error(
                "stars_successful_payment_invalid",
                telegram_id=message.from_user.id,
                reason=str(exc),
            )
            await message.answer("付款已收到，但紀錄驗證失敗。請聯絡 /paysupport。")
            return

        if delivered:
            await message.answer(
                f"付款成功，已解鎖「{tx.product}」。謝謝你的 {tx.amount_stars} Stars！"
            )
        else:
            await message.answer("這筆付款已處理過，權益不會重複發放。")

    @router.message(Command("refund_stars"))
    async def cmd_refund_stars(
        message: types.Message,
        bot: Bot,
        session: AsyncSession,
    ) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("用法：/refund_stars <telegram_payment_charge_id>")
            return

        service = StarsPaymentService(session)
        try:
            tx = await service.refund(bot=bot, charge_id=parts[1].strip())
        except PaymentValidationError as exc:
            await message.answer(str(exc))
            return
        await message.answer(f"已退款 {tx.amount_stars} Stars。")

    @router.message(Command("paysupport"))
    async def cmd_paysupport(message: types.Message) -> None:
        await message.answer(
            "付款支援：本服務只收 Telegram Stars（XTR）購買數位內容。\n"
            "若付款成功但權益未解鎖，請提供 Telegram 付款收據或 charge id。"
        )

    @router.message(Command("terms"))
    async def cmd_terms(message: types.Message) -> None:
        await message.answer(
            "服務條款摘要：\n"
            "1. Telegram Stars 僅用於購買本服務內的數位商品、虛擬權益或服務。\n"
            "2. 公開 Mini App 與付款頁面維持 SFW；成人內容需完成 18+ 驗證並主動開啟。\n"
            "3. 禁止非法內容；違規請求會被拒絕。\n"
            "4. 若發生付款或發放問題，請使用 /paysupport 聯絡處理。"
        )

    return router
