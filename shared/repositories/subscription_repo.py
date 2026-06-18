"""Async CRUD for Telegram Stars VIP subscriptions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.models import Subscription, User


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self, user_id: int) -> Subscription | None:
        """Return the user's active subscription, if any."""
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def get_valid_vip(self, user_id: int) -> Subscription | None:
        """Return subscription that currently grants VIP (active, cancelled, or grace)."""
        from datetime import timezone

        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                (
                    (
                        Subscription.status.in_(["active", "cancelled"])
                        & (Subscription.current_period_end > now)
                    )
                    | (
                        (Subscription.status == "grace")
                        & (Subscription.grace_period_end > now)
                    )
                ),
            )
        )
        return result.scalar_one_or_none()

    async def create_or_extend(
        self,
        *,
        user_id: int,
        current_period_end: datetime,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str | None = None,
    ) -> Subscription:
        """Upsert an active subscription for a user.

        If an active subscription already exists, extend its current_period_end.
        If a cancelled subscription exists, reactivate it.
        """
        now = datetime.now(timezone.utc)
        sub = await self.get_active(user_id)
        if sub is None:
            sub = Subscription(
                user_id=user_id,
                provider="stars",
                status="active",
                current_period_end=current_period_end,
                telegram_payment_charge_id=telegram_payment_charge_id,
                provider_payment_charge_id=provider_payment_charge_id,
                created_at=now,
                updated_at=now,
            )
            self.session.add(sub)
        else:
            sub.status = "active"
            sub.current_period_end = current_period_end
            sub.grace_period_end = None
            sub.cancelled_at = None
            sub.telegram_payment_charge_id = telegram_payment_charge_id
            if provider_payment_charge_id:
                sub.provider_payment_charge_id = provider_payment_charge_id
            sub.updated_at = now
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def cancel(self, user_id: int) -> Subscription | None:
        """Mark the active subscription as cancelled (keeps VIP until period_end)."""
        sub = await self.get_active(user_id)
        if sub is None:
            return None
        now = datetime.now(timezone.utc)
        sub.status = "cancelled"
        sub.cancelled_at = now
        sub.updated_at = now
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def start_grace(self, sub: Subscription) -> Subscription:
        """Move an active subscription whose payment failed into grace period."""
        settings = get_settings()
        now = datetime.now(timezone.utc)
        sub.status = "grace"
        sub.grace_period_end = now + timedelta(seconds=settings.vip_grace_period_seconds)
        sub.updated_at = now
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def expire(self, sub: Subscription) -> Subscription:
        """Move a grace subscription to expired."""
        now = datetime.now(timezone.utc)
        sub.status = "expired"
        sub.updated_at = now
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def process_expirations(self) -> tuple[int, int]:
        """Deactivate expired active subs and expired grace subs.

        Returns (grace_started_count, expired_count).
        """
        now = datetime.now(timezone.utc)
        grace_started = 0
        expired = 0

        # Active subscriptions past current_period_end -> grace
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.status == "active",
                Subscription.current_period_end <= now,
            )
        )
        for sub in result.scalars().all():
            await self.start_grace(sub)
            grace_started += 1

        # Grace subscriptions past grace_period_end -> expired
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.status == "grace",
                Subscription.grace_period_end <= now,
            )
        )
        for sub in result.scalars().all():
            await self.expire(sub)
            expired += 1

        return grace_started, expired


class EntitlementService:
    """Check VIP entitlements backed by subscriptions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sub_repo = SubscriptionRepository(session)

    async def is_vip(self, user_id: int) -> bool:
        """True if user has an active, cancelled-but-not-yet-expired, or grace-period subscription."""
        sub = await self.sub_repo.get_valid_vip(user_id)
        return sub is not None

    async def nsfw_allowed(self, user: User) -> bool:
        """NSFW content requires 18+ opt-in and active VIP."""
        if user.age_verified_at is None or not user.nsfw_opt_in:
            return False
        return await self.is_vip(user.telegram_id)

    async def subscription_status(self, user_id: int) -> dict:
        from datetime import timezone

        sub = await self.sub_repo.get_valid_vip(user_id)
        if sub is None:
            return {"is_vip": False, "status": "none", "expires_at": None}
        now = datetime.now(timezone.utc)
        if sub.status in ("active", "cancelled") and sub.current_period_end > now:
            return {
                "is_vip": True,
                "status": sub.status,
                "expires_at": sub.current_period_end.isoformat(),
            }
        if sub.status == "grace" and sub.grace_period_end and sub.grace_period_end > now:
            return {
                "is_vip": True,
                "status": "grace",
                "expires_at": sub.grace_period_end.isoformat(),
            }
        return {"is_vip": False, "status": sub.status, "expires_at": None}
