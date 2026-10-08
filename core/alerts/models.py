from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class AlertInbox(Base):
    """Dirección de reenvío de una cuenta (<buzón>+<token>@<dominio>) y lo último que llegó a ella."""

    __tablename__ = "alert_inboxes"
    __table_args__ = (
        Index("uq_alert_inboxes_user_id", "user_id", unique=True),
        Index("uq_alert_inboxes_token", "token", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Confirmación de reenvío de Gmail: el código se muestra en la app (nunca se abre el enlace del correo).
    forwarding_code: Mapped[str] = mapped_column(String(20), default="")
    forwarding_from: Mapped[str] = mapped_column(String(320), default="")
    last_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_count: Mapped[int] = mapped_column(Integer, default=0)
    last_summary: Mapped[str] = mapped_column(Text, default="")  # "LinkedIn: 6 nuevas, 2 repetidas"
    # Vacantes enviadas a analizar hoy (cada una gasta IA): tope diario por cuenta.
    quota_day: Mapped[date | None] = mapped_column(Date)
    quota_used: Mapped[int] = mapped_column(Integer, default=0)
    # Vacantes que llegaron y esperan cupo (o a que la persona registre su experiencia): JSON, lista de URLs.
    pending: Mapped[str] = mapped_column(Text, default="")
