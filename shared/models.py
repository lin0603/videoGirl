from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(128), index=True)
    display_name: Mapped[str | None] = mapped_column(String(256))
    age_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nsfw_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    locale: Mapped[str] = mapped_column(String(16), default="zh-TW")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Voice settings (task #9 integration). TTS is BreezyVoice-only.
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_provider: Mapped[str] = mapped_column(String(32), default="breezevoice")
    voice_slug: Mapped[str] = mapped_column(String(64), default="yiting")
    voice_speed: Mapped[float] = mapped_column(Float, default=1.0)
    voice_reference_audio_url: Mapped[str | None] = mapped_column(String(1024))
    voice_reference_audio_path: Mapped[str | None] = mapped_column(String(1024))


class PaymentTransaction(Base):
    """Telegram Stars payment transaction with idempotent delivery state."""

    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("payload", name="uq_payment_transactions_payload"),
        UniqueConstraint(
            "telegram_payment_charge_id",
            name="uq_payment_transactions_telegram_charge_id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), index=True
    )
    payload: Mapped[str] = mapped_column(String(128), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="invoice_created")
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(256), index=True)
    provider_payment_charge_id: Mapped[str | None] = mapped_column(String(256))
    invoice_link: Mapped[str | None] = mapped_column(String(2048))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship("User")


class Subscription(Base):
    """Telegram Stars recurring VIP subscription."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "status", name="uq_subscriptions_user_id_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="stars")
    status: Mapped[str] = mapped_column(String(32), default="active")
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    grace_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(256), index=True)
    provider_payment_charge_id: Mapped[str | None] = mapped_column(String(256))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship("User")


class CompanionMood(Base):
    """Internal mood state per (user, persona)."""

    __tablename__ = "companion_moods"
    __table_args__ = (
        UniqueConstraint("user_id", "persona_slug", name="uq_companion_moods_user_persona"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    persona_slug: Mapped[str] = mapped_column(String(64), index=True)
    affection: Mapped[float] = mapped_column(Float, default=0.0)
    longing: Mapped[float] = mapped_column(Float, default=0.0)
    playfulness: Mapped[float] = mapped_column(Float, default=0.0)
    upset: Mapped[float] = mapped_column(Float, default=0.0)
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Wallet(Base):
    """Stars-funded credit wallet (task #20)."""

    __tablename__ = "wallets"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), primary_key=True
    )
    balance: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CreditLedger(Base):
    """Atomic ledger entries for wallet credit changes."""

    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


class VoiceCategory(Base):
    """Admin-managed category for grouping voices."""

    __tablename__ = "voice_categories"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(BigInteger, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    voices: Mapped[list["Voice"]] = relationship(
        "Voice", back_populates="category", cascade="all, delete-orphan"
    )


class Voice(Base):
    """Backend-configurable voice catalog (admin-managed, task #7/#9)."""

    __tablename__ = "voices"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(32), default="breezevoice")
    # None -> use the BreezyVoice server's built-in default reference voice.
    reference_audio_path: Mapped[str | None] = mapped_column(String(1024))
    reference_transcript: Mapped[str | None] = mapped_column(String(2048))
    tempo: Mapped[float] = mapped_column(Float, default=1.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    category_slug: Mapped[str | None] = mapped_column(
        ForeignKey("voice_categories.slug"), nullable=True
    )
    category: Mapped[Optional["VoiceCategory"]] = relationship(
        "VoiceCategory", back_populates="voices"
    )


class Persona(Base):
    """Admin-managed character persona."""

    __tablename__ = "personas"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    greeting: Mapped[str] = mapped_column(Text, default="")
    nsfw_level: Mapped[int] = mapped_column(BigInteger, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
