"""Typed SQLAlchemy ORM models preserving existing table and column names."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative metadata for application persistence."""


class ModelSuccessLog(Base):
    """Successful AI model invocation statistics."""

    __tablename__ = "model_success_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=1)
    last_success_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    avg_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("provider", "model_name", name="_provider_model_uc"),)


class JailSentence(Base):
    """Persistent guild jail sentence and its expiry."""

    __tablename__ = "jail_sentences"

    guild_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(32), nullable=False)
    moderator_id: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
