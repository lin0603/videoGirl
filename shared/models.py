from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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

    # Voice settings (task #9 integration)
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_provider: Mapped[str] = mapped_column(String(32), default="edge-tts")
    voice_speed: Mapped[float] = mapped_column(Float, default=1.0)
    voice_reference_audio_url: Mapped[str | None] = mapped_column(String(1024))
    voice_reference_audio_path: Mapped[str | None] = mapped_column(String(1024))
