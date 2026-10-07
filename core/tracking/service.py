"""Casos de uso del seguimiento de postulaciones (una transacción por operación, dueño verificado)."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from core.capture import canonical_url
from core.db import session_scope
from core.profile.models import User
from core.profile.repository import NotFoundError
from core.tracking.models import (
    ACTIVE_STATUSES,
    APPLIED_STATUSES,
    STATUSES,
    TRIAGE_STATUSES,
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
    match_json: str = "",
    evidence_json: str = "",
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
            match_json=match_json, evidence_json=evidence_json, match_score=match_score, status=status,
            applied_on=applied_on,
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


def exists(username: str, application_id: int) -> bool:
    try:
        get_application(username, application_id)
    except NotFoundError:
        return False
    return True


def list_applications(
    username: str, statuses: tuple[str, ...] | None = None, *, with_files: bool = True
) -> list[Application]:
    """with_files=False no trae el PDF/DOCX de cada CV (listas, resumen, mercado): solo sus datos."""
    with session_scope() as s:
        query = select(Application).where(Application.user_id == _user_id(s, username))
        if statuses:
            query = query.where(Application.status.in_(statuses))
        cvs = selectinload(Application.cvs)
        if not with_files:
            cvs = cvs.defer(CVDocumentRecord.pdf).defer(CVDocumentRecord.docx)
        query = query.options(selectinload(Application.events), cvs)
        return list(s.scalars(query.order_by(Application.updated_at.desc(), Application.id.desc())))


def count(username: str, statuses: tuple[str, ...]) -> int:
    with session_scope() as s:
        query = select(func.count(Application.id)).where(
            Application.user_id == _user_id(s, username), Application.status.in_(statuses)
        )
        return s.scalar(query) or 0


def set_match(
    username: str, application_id: int, score: int, match_json: str = "", evidence_json: str = "",
    analysis_json: str = "",
) -> None:
    """Actualiza la compatibilidad guardada. Las evidencias apuntan a los requisitos por número: si la
    vacante se volvió a leer con la IA, su análisis (`analysis_json`) debe guardarse junto con ellas."""
    with session_scope() as s:
        application = _owned(s, username, application_id)
        if analysis_json:
            application.analysis_json = analysis_json
        application.match_score = score
        if match_json:
            application.match_json = match_json
        if evidence_json:
            application.evidence_json = evidence_json


_TRACKING_PARAMS = re.compile(
    r"^(utm_\w*|trk\w*|refid|trackingid|position|pagenum|gclid|fbclid|msclkid|mc_\w+|_ga|ref|ref_src|src|source|origin|si)$", re.I
)


def normalize_url(url: str) -> str:
    """Clave de una vacante: host/ruta de la URL canónica + parámetros que la identifican (p. ej. `?jk=`),
    sin los de seguimiento. Ante la duda se conserva el parámetro: un duplicado es mejor que mezclar dos vacantes."""
    try:
        parsed = urlparse(canonical_url(url))
        hostname = parsed.hostname
    except ValueError:  # enlace mal formado: no se compara con nada
        return ""
    if not hostname:
        return ""
    key = f"{hostname.lower().removeprefix('www.')}{parsed.path.rstrip('/')}"
    params = sorted((k, v) for k, v in parse_qsl(parsed.query) if not _TRACKING_PARAMS.match(k))
    return f"{key}?{urlencode(params)}" if params else key


def find_by_url(username: str, url: str) -> Application | None:
    key = normalize_url(url)
    if not key:
        return None
    with session_scope() as s:  # sin cargar eventos ni CVs: se llama por cada enlace de la bandeja
        query = select(Application).where(Application.user_id == _user_id(s, username), Application.url != "")
        return next((a for a in s.scalars(query.order_by(Application.id.desc())) if normalize_url(a.url) == key), None)


def delete_application(username: str, application_id: int) -> None:
    with session_scope() as s:
        s.delete(_owned(s, username, application_id))


# ── CVs: el correcto para cada vacante ───────────────────────────────


def attach_cv(
    username: str, application_id: int, *, pdf: bytes, docx: bytes, markdown: str, language: str, filename: str,
    document_json: str = "",
) -> int:
    with session_scope() as s:
        application = _owned(s, username, application_id)
        record = CVDocumentRecord(
            pdf=pdf, docx=docx, markdown=markdown, language=language, filename=filename, document_json=document_json,
            pdf_sha256=sha256(pdf), docx_sha256=sha256(docx),
        )
        application.cvs.append(record)
        s.flush()
        _event(application, "cv_generado", f"CV #{record.id} · huella {record.pdf_sha256[:12]}")
        if application.status in (*TRIAGE_STATUSES, "guardada"):
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


def get_cv(username: str, cv_id: int) -> CVDocumentRecord:
    """Un CV guardado, solo si pertenece a una postulación del usuario."""
    with session_scope() as s:
        record = s.scalar(
            select(CVDocumentRecord).join(Application)
            .where(CVDocumentRecord.id == cv_id, Application.user_id == _user_id(s, username))
        )
        if record is None:
            raise NotFoundError(f"CV {cv_id}")
        return record


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
    # La bandeja (por revisar) y lo descartado sin enviar no son postulaciones.
    applications = [
        a for a in list_applications(username, with_files=False)
        if a.status not in TRIAGE_STATUSES and not (a.status == "descartada" and a.applied_on is None)
    ]
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
