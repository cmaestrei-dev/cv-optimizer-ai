from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class BotToken(Base):
    """Token de larga duración para el bot local. Solo se guarda su huella: el texto se muestra una vez."""

    __tablename__ = "bot_tokens"
    __table_args__ = (
        Index("uq_bot_tokens_token_hash", "token_hash", unique=True),
        Index("ix_bot_tokens_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(60), default="")
    token_hash: Mapped[str] = mapped_column(String(64))
    hint: Mapped[str] = mapped_column(String(8), default="")  # últimos 4 caracteres, para reconocerlo
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
