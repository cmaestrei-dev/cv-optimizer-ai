"""Seguimiento de postulaciones: postulación, historial inmutable de eventos y CVs generados."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base

STATUSES: dict[str, tuple[str, str]] = {
    "guardada": ("Guardada", ":material/bookmark:"),
    "cv_generado": ("CV listo", ":material/description:"),
    "postulada": ("Postulada", ":material/send:"),
    "en_revision": ("En revisión", ":material/hourglass_top:"),
    "entrevista": ("Entrevista", ":material/groups:"),
    "oferta": ("Oferta", ":material/celebration:"),
    "rechazada": ("Rechazada", ":material/block:"),
    "retirada": ("Retirada", ":material/logout:"),
}
ACTIVE_STATUSES = ("guardada", "cv_generado", "postulada", "en_revision", "entrevista")
APPLIED_STATUSES = ("postulada", "en_revision", "entrevista", "oferta", "rechazada")  # ya se envió
PLATFORMS = ["LinkedIn", "Computrabajo", "Magneto", "elempleo", "Página de la empresa", "Correo o referido", "Otra"]


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String)
    company: Mapped[str] = mapped_column(String, default="")
    platform: Mapped[str] = mapped_column(String, default="")
    url: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String(30), default="guardada", index=True)
    vacancy_text: Mapped[str] = mapped_column(Text, default="")
    analysis_json: Mapped[str] = mapped_column(Text, default="")  # VacancyAnalysis para la analítica (fase 3)
    match_score: Mapped[int | None] = mapped_column(Integer)
    applied_on: Mapped[date | None] = mapped_column(Date)
    next_action_on: Mapped[date | None] = mapped_column(Date, index=True)
    next_action: Mapped[str] = mapped_column(String, default="")
    contact: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ApplicationEvent.id",
    )
    cvs: Mapped[list["CVDocumentRecord"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True,
        order_by="CVDocumentRecord.id",
    )


class ApplicationEvent(Base):
    """Historial de solo-agregar: no existe código que edite o borre eventos (salvo al borrar la postulación)."""

    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # creada, cv_generado, cv_enviado, estado, nota, recordatorio, datos
    from_status: Mapped[str] = mapped_column(String(30), default="")
    to_status: Mapped[str] = mapped_column(String(30), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped[Application] = relationship(back_populates="events")


class CVDocumentRecord(Base):
    """Copia exacta de cada CV generado para una postulación, con su huella SHA-256."""

    __tablename__ = "cv_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    language: Mapped[str] = mapped_column(String(10), default="es")
    markdown: Mapped[str] = mapped_column(Text, default="")
    pdf: Mapped[bytes] = mapped_column(LargeBinary)
    docx: Mapped[bytes] = mapped_column(LargeBinary)
    pdf_sha256: Mapped[str] = mapped_column(String(64))
    docx_sha256: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String, default="cv.pdf")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped[Application] = relationship(back_populates="cvs")
