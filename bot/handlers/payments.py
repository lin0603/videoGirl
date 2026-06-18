from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.logging import get_logger
from shared.repositories.subscription_repo import EntitlementService
from shared.subscriptions import (
    SubscriptionValidationError,
    cancel_subscription,
    create_invoice_link,
    handle_successful_payment,
    is_vip_payload,
    validate_pre_checkout,
)
from shared.wallet import WalletService


def _is_admin(telegram_id: int) -> bool:
    ids = {x.strip() for x in (settings.admin_telegram_ids or "").split(",") if x.strip()}
    return str(telegram_id) in ids

from shared.gifts import (
    GIFT_CATALOG,
    create_gift_invoice,
    is_gift_payload,
    is_unlock_payload,
    parse_gift_key,
    parse_unlock_key,
    record_gift,
    record_unlock,
)
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
            + "\n\n用 /buy <商品代碼> 開立 Telegram Stars 發票。\n"
            "或輸入 /subscribe 訂閱 VIP 月方案。"
        )

    @router.message(Command("gift"))
    async def cmd_gift(message: types.Message, bot: Bot) -> None:
        """Send a virtual gift to the girlfriend via Stars payment."""
        parts = (message.text or "").split(maxsplit=1)
        gift_key = parts[1].strip().lower() if len(parts) > 1 else ""

        if not gift_key:
            lines = [
                f"・<code>{item.key}</code> {item.emoji} {item.title}（{item.stars} Stars）"
                for item in GIFT_CATALOG.values()
            ]
            await message.answer(
                "可以送女友的禮物：\n"
                + "\n".join(lines)
                + "\n\n用 /gift <禮物代碼> 送出禮物，她會很感動喔 💕"
            )
            return

        if gift_key not in GIFT_CATALOG:
            await message.answer("沒有這個禮物。請用 /gift 查看禮物清單。")
            return

        link = await create_gift_invoice(bot, message.from_user.id, gift_key)
        item = GIFT_CATALOG[gift_key]
        await message.answer(
            f"送出 {item.emoji} {item.title} 給她吧！",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                types.InlineKeyboardButton(
                    text=f"付款 {item.stars} Stars",
                    url=link,
                )
            ]]),
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

    @router.message(Command("subscribe"))
    async def cmd_subscribe(message: types.Message, bot: Bot) -> None:
        link = await create_invoice_link(bot, message.from_user.id)
        await message.answer(
            "💎 <b>VIP 月訂閱</b>\n\n"
            f"每月 {settings.vip_amount_stars} Stars，解鎖無限聊天、NSFW 內容與更高媒體配額。\n"
            "點下面連結付款後會自動開通：\n"
            f'<a href="{link}">立即訂閱 VIP</a>',
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    @router.message(Command("vip_status"))
    async def cmd_vip_status(message: types.Message, session: AsyncSession) -> None:
        status = await EntitlementService(session).subscription_status(message.from_user.id)
        if not status["is_vip"]:
            await message.answer(
                "你目前不是 VIP。輸入 /subscribe 可訂閱月方案。"
            )
            return
        status_text = "生效中" if status["status"] == "active" else "寬限期"
        await message.answer(
            f"💎 VIP 狀態：<b>{status_text}</b>\n"
            f"到期時間：{status['expires_at']}\n"
            "想取消自動續訂請輸入 /cancel_vip。",
            parse_mode="HTML",
        )

    @router.message(Command("cancel_vip"))
    async def cmd_cancel_vip(message: types.Message, session: AsyncSession) -> None:
        ok = await cancel_subscription(session, message.from_user.id)
        if ok:
            await message.answer(
                "已為你取消 VIP 自動續訂。權益會持續到本期結束。"
            )
        else:
            await message.answer("你目前沒有生效中的 VIP 訂閱。")

    @router.pre_checkout_query()
    async def on_pre_checkout(
        query: types.PreCheckoutQuery,
        session: AsyncSession,
    ) -> None:
        if is_vip_payload(query.invoice_payload):
            try:
                await validate_pre_checkout(query)
            except SubscriptionValidationError as exc:
                logger.warning(
                    "vip_pre_checkout_rejected",
                    telegram_id=query.from_user.id,
                    payload=query.invoice_payload,
                    reason=str(exc),
                )
                await query.answer(ok=False, error_message=str(exc))
                return
            await query.answer(ok=True)
            return

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

    @router.message(F.successful_payment)
    async def on_successful_payment(
        message: types.Message,
        session: AsyncSession,
    ) -> None:
        payment = message.successful_payment
        if is_gift_payload(payment.invoice_payload):
            gift_record, is_new = await record_gift(session, message.from_user.id, payment)
            if is_new:
                from shared.gifts import GIFT_CATALOG
                from shared.mood import MoodService
                from orchestrator.persona import get_persona
                item = GIFT_CATALOG.get(gift_record.gift_key)
                emoji = item.emoji if item else "🎁"
                # Boost companion mood using the gift event.
                persona = get_persona()
                mood_svc = MoodService(session)
                await mood_svc.process_event(
                    message.from_user.id,
                    persona.slug,
                    "gift",
                )
                await message.answer(
                    f"謝謝你送的 {emoji}！她看到一定很開心 💕"
                )
            else:
                await message.answer("這份禮物已記錄過，不會重複計算。")
            return

        if is_unlock_payload(payment.invoice_payload):
            item_key = parse_unlock_key(payment.invoice_payload) or "unknown"
            _unlock, is_new = await record_unlock(session, message.from_user.id, item_key, payment)
            if is_new:
                await message.answer(f"解鎖成功！「{item_key}」已永久解鎖 🔓")
            else:
                await message.answer("這個解鎖已記錄過，不會重複發放。")
            return

        if is_vip_payload(payment.invoice_payload):
            try:
                _, is_new = await handle_successful_payment(
                    session,
                    message.from_user.id,
                    payment,
                )
            except SubscriptionValidationError as exc:
                logger.error(
                    "vip_payment_invalid",
                    telegram_id=message.from_user.id,
                    reason=str(exc),
                )
                await message.answer("付款已收到，但訂閱驗證失敗。請聯絡 /paysupport。")
                return

            if is_new:
                await message.answer(
                    "🎉 VIP 訂閱開通成功！現在你可以無限聊天、解鎖 NSFW 內容。"
                )
            else:
                await message.answer(
                    "💎 VIP 訂閱已續訂成功，感謝你的支持！"
                )
            return

        service = StarsPaymentService(session)
        try:
            tx, delivered = await service.record_successful_payment(
                user_id=message.from_user.id,
                payment=payment,
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
            from shared.payments import credits_amount_from_slug

            credits = credits_amount_from_slug(tx.product)
            if credits:
                await WalletService(session).top_up(
                    message.from_user.id,
                    credits,
                    reason="stars_topup",
                    reference=tx.telegram_payment_charge_id,
                )
                await message.answer(
                    f"付款成功！已儲值 {credits} 點到你的錢包。\n"
                    f"目前餘額：{await WalletService(session).get_balance(message.from_user.id)} 點。"
                )
            else:
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
        if not _is_admin(message.from_user.id):
            logger.warning("refund_denied_non_admin", telegram_id=message.from_user.id)
            await message.answer("此指令僅限管理員使用。")
            return
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

    @router.message(Command("wallet"))
    async def cmd_wallet(message: types.Message, session: AsyncSession) -> None:
        balance = await WalletService(session).get_balance(message.from_user.id)
        await message.answer(
            f"💰 你的點數錢包餘額：<b>{balance}</b> 點\n"
            "圖片、語音、影片生成會從這裡扣點。\n"
            "輸入 /topup 儲值。",
            parse_mode="HTML",
        )

    @router.message(Command("topup"))
    async def cmd_topup(message: types.Message, session: AsyncSession) -> None:
        parts = (message.text or "").split(maxsplit=1)
        slug = parts[1].strip() if len(parts) > 1 else "credits_100"
        service = StarsPaymentService(session)
        try:
            tx, product = await service.create_invoice_payload(
                user_id=message.from_user.id,
                product_slug=slug,
            )
        except UnknownProductError:
            await message.answer("找不到這個儲值方案。目前可用：/buy credits_100")
            return

        await message.answer_invoice(
            title=product.title,
            description=product.description,
            payload=tx.payload,
            currency=STARS_CURRENCY,
            provider_token=STARS_PROVIDER_TOKEN,
            prices=[types.LabeledPrice(label=product.title, amount=product.amount_stars)],
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

    @router.message(Command("stars_balance"))
    async def cmd_stars_balance(message: types.Message, bot: Bot) -> None:
        if not _is_admin(message.from_user.id):
            await message.answer("此指令僅供管理員使用。")
            return
        from shared.compliance import get_stars_status
        status = await get_stars_status(bot)
        await message.answer(status.message)

    return router
