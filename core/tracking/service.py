"""Casos de uso del seguimiento de postulaciones (una transacción por operación, dueño verificado)."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.db import session_scope
from core.profile.models import User
from core.profile.repository import NotFoundError
from core.tracking.models import (
    ACTIVE_STATUSES,
    APPLIED_STATUSES,
    STATUSES,
    Application,
    ApplicationEvent,
    CVDocumentRecord,
)

TIMEZONE = ZoneInfo("America/Bogota")
DEFAULT_FOLLOW_UP_DAYS = 7


def today() -> date:
    return datetime.now(TIMEZONE).date()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _user_id(session: Session, username: str) -> int:
    user_id = session.scalar(select(User.id).where(User.username == username))
    if user_id is None:
        raise NotFoundError(f"Usuario {username}")
    return user_id


def _owned(session: Session, username: str, application_id: int) -> Application:
    application = session.scalar(
        select(Application)
        .where(Application.id == application_id, Application.user_id == _user_id(session, username))
        .options(selectinload(Application.events), selectinload(Application.cvs))
    )
    if application is None:
        raise NotFoundError(f"Postulación {application_id}")
    return application


def _event(application: Application, kind: str, detail: str = "", from_status: str = "", to_status: str = "") -> None:
    application.events.append(ApplicationEvent(kind=kind, detail=detail, from_status=from_status, to_status=to_status))
    application.updated_at = datetime.now(UTC)  # cualquier actividad la sube en la lista


def _set_status(application: Application, status: str, note: str = "") -> None:
    if status not in STATUSES:
        raise ValueError(f"Estado desconocido: {status}")
    if status == application.status:
        return
    _event(application, "estado", note, application.status, status)
    application.status = status


# ── crear y consultar ─────────────────────────────────────────────────


def create_application(
    username: str,
    *,
    role: str,
    company: str = "",
    platform: str = "",
    url: str = "",
    vacancy_text: str = "",
    analysis_json: str = "",
    match_score: int | None = None,
    status: str = "guardada",
    applied_on: date | None = None,
) -> int:
    if status not in STATUSES:
        raise ValueError(f"Estado desconocido: {status}")
    with session_scope() as s:
        application = Application(
            user_id=_user_id(s, username), role=role.strip() or "(sin cargo)", company=company.strip(),
            platform=platform, url=url.strip(), vacancy_text=vacancy_text, analysis_json=analysis_json,
            match_score=match_score, status=status, applied_on=applied_on,
        )
        if status in APPLIED_STATUSES and applied_on:
            application.next_action_on = applied_on + timedelta(days=DEFAULT_FOLLOW_UP_DAYS)
            application.next_action = "Hacer seguimiento si no hay respuesta"
        s.add(application)
        _event(application, "creada", f"{role} — {company}".strip(" —"), to_status=status)
        s.flush()
        return application.id


def get_application(username: str, application_id: int) -> Application:
    with session_scope() as s:
        return _owned(s, username, application_id)


def list_applications(username: str, statuses: tuple[str, ...] | None = None) -> list[Application]:
    with session_scope() as s:
        query = select(Application).where(Application.user_id == _user_id(s, username))
        if statuses:
            query = query.where(Application.status.in_(statuses))
        query = query.options(selectinload(Application.events), selectinload(Application.cvs))
        return list(s.scalars(query.order_by(Application.updated_at.desc(), Application.id.desc())))


def delete_application(username: str, application_id: int) -> None:
    with session_scope() as s:
        s.delete(_owned(s, username, application_id))


# ── CVs: el correcto para cada vacante ───────────────────────────────


def attach_cv(username: str, application_id: int, *, pdf: bytes, docx: bytes, markdown: str, language: str, filename: str) -> int:
    with session_scope() as s:
        application = _owned(s, username, application_id)
        record = CVDocumentRecord(
            pdf=pdf, docx=docx, markdown=markdown, language=language, filename=filename,
            pdf_sha256=sha256(pdf), docx_sha256=sha256(docx),
        )
        application.cvs.append(record)
        s.flush()
        _event(application, "cv_generado", f"CV #{record.id} · huella {record.pdf_sha256[:12]}")
        if application.status == "guardada":
            _set_status(application, "cv_generado")
        return record.id


def mark_sent(username: str, application_id: int, cv_id: int | None, *, sent_on: date | None = None, platform: str = "") -> None:
    """Registra el envío. El CV debe ser uno generado PARA ESTA postulación (garantía de CV correcto)."""
    with session_scope() as s:
        application = _owned(s, username, application_id)
        record = None
        if cv_id is not None:
            record = next((c for c in application.cvs if c.id == cv_id), None)
            if record is None:
                raise NotFoundError(f"El CV {cv_id} no pertenece a esta postulación")
            record.sent_at = datetime.now(UTC)
        sent_on = sent_on or today()
        application.applied_on = sent_on
        if platform:
            application.platform = platform
        detail = f"Enviada por {application.platform or 'canal no indicado'} el {sent_on.isoformat()}"
        if record is not None:
            detail += f" · CV #{record.id} · huella {record.pdf_sha256[:12]}"
        _event(application, "cv_enviado", detail)
        _set_status(application, "postulada")
        application.next_action_on = sent_on + timedelta(days=DEFAULT_FOLLOW_UP_DAYS)
        application.next_action = "Hacer seguimiento si no hay respuesta"


def verify_cv(record: CVDocumentRecord) -> bool:
    """True si el PDF guardado es exactamente el mismo que se registró (no fue alterado)."""
    return sha256(record.pdf) == record.pdf_sha256 and sha256(record.docx) == record.docx_sha256


# ── estado, notas y recordatorios ────────────────────────────────────


def change_status(username: str, application_id: int, status: str, note: str = "") -> None:
    with session_scope() as s:
        application = _owned(s, username, application_id)
        _set_status(application, status, note.strip())
        if status not in ACTIVE_STATUSES:
            application.next_action_on, application.next_action = None, ""


def add_note(username: str, application_id: int, note: str) -> None:
    if not note.strip():
        return
    with session_scope() as s:
        _event(_owned(s, username, application_id), "nota", note.strip())


def set_follow_up(username: str, application_id: int, when: date | None, what: str = "") -> None:
    with session_scope() as s:
        application = _owned(s, username, application_id)
        application.next_action_on, application.next_action = when, what.strip()
        _event(application, "recordatorio", f"{when.isoformat()}: {what.strip()}" if when else "Recordatorio quitado")


def update_details(username: str, application_id: int, **fields: str) -> None:
    with session_scope() as s:
        application = _owned(s, username, application_id)
        changed = []
        for key in ("role", "company", "platform", "url", "contact"):
            if key in fields and fields[key].strip() != getattr(application, key):
                setattr(application, key, fields[key].strip())
                changed.append(key)
        if changed:
            _event(application, "datos", "Actualizado: " + ", ".join(changed))


# ── resumen ──────────────────────────────────────────────────────────


@dataclass
class Summary:
    total: int
    by_status: dict[str, int]
    sent: int
    responses: int
    due: list[Application]

    @property
    def response_rate(self) -> float | None:
        """De las enviadas, cuántas avanzaron (revisión, entrevista u oferta) o recibieron respuesta."""
        return self.responses / self.sent if self.sent else None


def summary(username: str, on: date | None = None) -> Summary:
    on = on or today()
    applications = list_applications(username)
    by_status = dict.fromkeys(STATUSES, 0)
    for a in applications:
        by_status[a.status] += 1
    sent = sum(by_status[k] for k in APPLIED_STATUSES)
    responses = sum(by_status[k] for k in ("en_revision", "entrevista", "oferta", "rechazada"))
    due = sorted(
        (a for a in applications if a.next_action_on and a.next_action_on <= on and a.status in ACTIVE_STATUSES),
        key=lambda a: a.next_action_on,
    )
    return Summary(len(applications), by_status, sent, responses, due)
