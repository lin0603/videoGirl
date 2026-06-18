"""Stars-funded credit wallet core (task #20).

Provides atomic top-up and debit operations backed by a ledger table.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.logging import get_logger
from shared.models import CreditLedger, Wallet

logger = get_logger("shared.wallet")


class InsufficientCreditsError(ValueError):
    pass


class WalletService:
    """Atomic credit wallet operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_wallet(self, user_id: int) -> Wallet:
        result = await self.session.execute(
            select(Wallet).where(Wallet.user_id == user_id)
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            wallet = Wallet(user_id=user_id, balance=0)
            self.session.add(wallet)
            await self.session.flush()
        return wallet

    async def get_balance(self, user_id: int) -> int:
        wallet = await self.get_or_create_wallet(user_id)
        return wallet.balance

    async def top_up(
        self,
        user_id: int,
        amount: int,
        *,
        reason: str,
        reference: str | None = None,
    ) -> Wallet:
        """Add credits atomically and record a ledger entry."""
        if amount <= 0:
            raise ValueError("top_up amount must be positive")

        wallet = await self._lock_wallet(user_id)
        wallet.balance += amount
        wallet.updated_at = datetime.now(timezone.utc)

        entry = CreditLedger(
            user_id=user_id,
            delta=amount,
            balance_after=wallet.balance,
            reason=reason,
            reference=reference,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(wallet)

        logger.info(
            "wallet_top_up",
            user_id=user_id,
            amount=amount,
            balance=wallet.balance,
            reason=reason,
        )
        return wallet

    async def debit(
        self,
        user_id: int,
        amount: int,
        *,
        reason: str,
        reference: str | None = None,
    ) -> Wallet:
        """Deduct credits atomically. Raises InsufficientCreditsError if balance is too low."""
        if amount <= 0:
            raise ValueError("debit amount must be positive")

        wallet = await self._lock_wallet(user_id)
        if wallet.balance < amount:
            logger.warning(
                "wallet_debit_insufficient",
                user_id=user_id,
                amount=amount,
                balance=wallet.balance,
                reason=reason,
            )
            raise InsufficientCreditsError(
                f"點數不足：需要 {amount} 點，目前只有 {wallet.balance} 點。"
            )

        wallet.balance -= amount
        wallet.updated_at = datetime.now(timezone.utc)

        entry = CreditLedger(
            user_id=user_id,
            delta=-amount,
            balance_after=wallet.balance,
            reason=reason,
            reference=reference,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(wallet)

        logger.info(
            "wallet_debit",
            user_id=user_id,
            amount=amount,
            balance=wallet.balance,
            reason=reason,
        )
        return wallet

    async def _lock_wallet(self, user_id: int) -> Wallet:
        """Select the wallet row with FOR UPDATE for atomic read-modify-write."""
        result = await self.session.execute(
            select(Wallet)
            .where(Wallet.user_id == user_id)
            .with_for_update()
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            wallet = Wallet(user_id=user_id, balance=0)
            self.session.add(wallet)
            await self.session.flush()
        return wallet

    async def ledger(self, user_id: int, limit: int = 20) -> list[CreditLedger]:
        """Return recent ledger entries for a user."""
        result = await self.session.execute(
            select(CreditLedger)
            .where(CreditLedger.user_id == user_id)
            .order_by(CreditLedger.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
