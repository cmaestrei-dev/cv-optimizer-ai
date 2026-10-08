"""Alertas de empleo por correo → bandeja.

La persona reenvía (con un filtro de Gmail) las alertas de los portales a su dirección
<buzón>+<token>@<dominio>. `check()` lee el buzón de la app, reconoce de quién es cada correo, saca los
enlaces de vacantes y los manda al mismo trabajo "bandeja" de los enlaces pegados. Cada correo se manda a
la papelera después de leerlo: no se guardan correos.

Variables: ALERTS_MAILBOX (dirección del buzón), ALERTS_MAILBOX_PASSWORD (contraseña de aplicación),
ALERTS_IMAP_HOST (por defecto Gmail) y ALERTS_DAILY_LINKS (vacantes por cuenta al día que se mandan a
analizar; cada una gasta IA).
"""

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core import discovery
from core.alerts import parsing
from core.alerts.mailbox import open_mailbox
from core.alerts.models import AlertInbox
from core.db import session_scope
from core.errors import UserInputError
from core.jobs import service as jobs
from core.profile import service as profiles
from core.profile.models import User
from core.profile.repository import NotFoundError
from core.tracking import service as tracking

logger = logging.getLogger(__name__)

DEFAULT_DAILY_LINKS = 40
MIN_INTERVAL = 60  # segundos entre revisiones del buzón (la pide cualquiera que abra la bandeja)
MAX_MESSAGES = 50  # por revisión
MAX_WAITING = 100  # vacantes en espera por cuenta (las más nuevas se descartan si se llena)
MAX_FAILURES = 3


@dataclass(frozen=True)
class AlertStatus:
    enabled: bool  # el servidor tiene buzón configurado
    address: str = ""  # vacío = la cuenta aún no activó las alertas
    forwarding_code: str = ""
    forwarding_from: str = ""
    last_received_at: datetime | None = None
    received_count: int = 0
    last_summary: str = ""
    waiting: int = 0
    ignored_recently: int = 0  # correos que no son alertas en los últimos días (todos, si siguen llegando)


@dataclass
class CheckReport:
    checked: bool  # False: se revisó hace poco u otra revisión está en curso
    messages: int = 0
    alerts: int = 0
    queued: int = 0
    rejected: int = 0


def mailbox_address() -> str:
    return os.environ.get("ALERTS_MAILBOX", "").strip().lower()


def _password() -> str:
    return "".join(os.environ.get("ALERTS_MAILBOX_PASSWORD", "").split())


def enabled() -> bool:
    return "@" in mailbox_address() and bool(_password())


def daily_links() -> int:
    try:
        return max(0, int(os.environ.get("ALERTS_DAILY_LINKS", DEFAULT_DAILY_LINKS)))
    except ValueError:
        return DEFAULT_DAILY_LINKS


def _address(token: str) -> str:
    local, _, domain = mailbox_address().partition("@")
    return f"{local}+{token}@{domain}"


def _user_id(session, username: str) -> int:
    user_id = session.scalar(select(User.id).where(User.username == username))
    if user_id is None:
        raise NotFoundError(f"Usuario {username}")
    return user_id


def _view(inbox: AlertInbox | None) -> AlertStatus:
    if inbox is None:
        return AlertStatus(enabled=True)
    return AlertStatus(
        enabled=True, address=_address(inbox.token), forwarding_code=inbox.forwarding_code,
        forwarding_from=inbox.forwarding_from, last_received_at=inbox.last_received_at,
        received_count=inbox.received_count, last_summary=inbox.last_summary, waiting=len(_waiting(inbox)),
        ignored_recently=inbox.ignored_count if _recent(inbox.last_ignored_at) else 0,
    )


def _recent(when: datetime | None, days: int = 3) -> bool:
    if when is None:
        return False
    if when.tzinfo is None:  # SQLite guarda sin zona: es UTC
        when = when.replace(tzinfo=UTC)
    return datetime.now(UTC) - when < timedelta(days=days)


def status(username: str) -> AlertStatus:
    if not enabled():
        return AlertStatus(enabled=False)
    with session_scope() as s:
        user_id = _user_id(s, username)
        return _view(s.scalar(select(AlertInbox).where(AlertInbox.user_id == user_id)))


def activate(username: str, *, rotate: bool = False) -> AlertStatus:
    """Crea la dirección de la cuenta (o una nueva si `rotate`: la anterior deja de funcionar)."""
    if not enabled():
        raise UserInputError("Las alertas por correo no están disponibles en este servidor.")
    try:
        with session_scope() as s:
            user_id = _user_id(s, username)
            inbox = s.scalar(select(AlertInbox).where(AlertInbox.user_id == user_id))
            if inbox is None:
                inbox = AlertInbox(user_id=user_id, token=secrets.token_hex(12))
                s.add(inbox)
            elif rotate:
                inbox.token, inbox.forwarding_code, inbox.forwarding_from = secrets.token_hex(12), "", ""
                inbox.ignored_count, inbox.last_ignored_at = 0, None
            s.flush()
            return _view(inbox)
    except IntegrityError:  # dos activaciones a la vez: gana la primera
        return status(username)


# ── lectura del buzón ─────────────────────────────────────────────────

_lock = threading.Lock()
_last_check = float("-inf")
_failures: dict[str, int] = {}  # huella del correo → intentos fallidos (en memoria: basta con un proceso)


def check(*, force: bool = False, opener: Callable[[], AbstractContextManager] | None = None) -> CheckReport:
    """Procesa los correos del buzón (de todas las cuentas) y lo que esperaba cupo.

    Un correo que falla (p. ej. la base no responde) se queda para la próxima revisión, sin frenar a los
    demás; tras MAX_FAILURES intentos se descarta. Varios fallos seguidos detienen la revisión."""
    global _last_check
    if not enabled() or not _lock.acquire(blocking=False):
        return CheckReport(checked=False)
    try:
        if not force and time.monotonic() - _last_check < MIN_INTERVAL:
            return CheckReport(checked=False)
        _last_check = time.monotonic()
        report = CheckReport(checked=True)
        host = os.environ.get("ALERTS_IMAP_HOST", "").strip() or "imap.gmail.com"
        with (opener or (lambda: open_mailbox(mailbox_address(), _password(), host)))() as box:
            in_a_row = 0
            for uid, raw in box.fetch(MAX_MESSAGES):
                report.messages += 1
                if not _process(raw, report):
                    in_a_row += 1
                    if in_a_row >= 3:
                        break
                    continue
                in_a_row = 0
                box.discard(uid)
            box.empty_trash()
        _drain_waiting(report)
        return report
    finally:
        _lock.release()


def _process(raw: bytes, report: CheckReport) -> bool:
    """True si el correo ya se puede borrar."""
    try:
        parsed = parsing.parse(raw, mailbox_address())
    except Exception:  # un correo ilegible no debe trabar el buzón
        logger.exception("Correo de alerta ilegible")
        parsed = parsing.ParsedAlert("rechazado", reason="correo ilegible")
    try:
        _handle(parsed, report)
        return True
    except Exception:
        key = hashlib.sha256(raw).hexdigest()
        if len(_failures) > 1000:
            _failures.clear()
        _failures[key] = _failures.get(key, 0) + 1
        if _failures[key] < MAX_FAILURES:
            logger.exception("No se pudo procesar un correo de alerta (intento %s)", _failures[key])
            return False
        logger.exception("Correo de alerta descartado tras %s intentos", MAX_FAILURES)
        _failures.pop(key, None)
        return True


def _handle(parsed: parsing.ParsedAlert, report: CheckReport) -> None:
    if parsed.kind == "rechazado":
        report.rejected += 1
        logger.info("Correo descartado: %s (remitente: %s)", parsed.reason,
                    parsed.sender or parsed.sender_domain or "-")  # solo portales: de los demás no se registra nada
        if parsed.foreign and parsed.token:
            with session_scope() as s:
                if (inbox := s.scalar(select(AlertInbox).where(AlertInbox.token == parsed.token))) is not None:
                    inbox.ignored_count += 1
                    inbox.last_ignored_at = datetime.now(UTC)
        return
    with session_scope() as s:
        inbox = s.scalar(select(AlertInbox).where(AlertInbox.token == parsed.token))
        if inbox is None:  # dirección cambiada o inventada
            report.rejected += 1
            logger.info("Correo para una dirección que no existe (remitente: %s)", parsed.sender_domain)
            return
        if parsed.kind == "confirmacion":
            inbox.forwarding_code, inbox.forwarding_from = parsed.forwarding_code, parsed.forwarding_from[:320]
            logger.info("Llegó el código de confirmación del reenvío de Gmail")
            return
        inbox_id = inbox.id
    logger.info("Alerta de %s con %s vacantes", parsed.sender, len(parsed.links))
    result = _enqueue(inbox_id, [link.url for link in parsed.links], received=True)
    with session_scope() as s:
        s.get(AlertInbox, inbox_id).last_summary = _summary(parsed.portal, len(parsed.links), result)
    report.alerts += 1
    report.queued += result.queued


@dataclass
class _Result:
    queued: int = 0
    repeated: int = 0  # de las que llegaron: ya estaban en la bandeja, en postulaciones o en análisis
    waiting: int = 0
    has_experience: bool = True


def _enqueue(inbox_id: int, incoming: list[str], *, received: bool) -> _Result:
    """Manda a analizar lo que espera y lo que llegó, hasta el tope del día; el resto queda esperando.
    Las lecturas van fuera de la transacción; el cupo, la espera y los trabajos se guardan juntos."""
    with session_scope() as s:
        inbox = s.get(AlertInbox, inbox_id)
        user_id, waiting = inbox.user_id, _waiting(inbox)
        username = s.scalar(select(User.username).where(User.id == user_id))
        in_analysis = {u for p in jobs.pending_payloads(s, user_id, "alerta") for u in p.get("urls", [])}
    candidates = list(dict.fromkeys(waiting + incoming))
    new = [u for u in candidates if u not in in_analysis and tracking.find_by_url(username, u) is None]
    result = _Result(repeated=len([u for u in dict.fromkeys(incoming) if u not in new]))
    result.has_experience = not new or bool(profiles.snapshot(username).experiences)
    with session_scope() as s:
        inbox = s.get(AlertInbox, inbox_id)
        today = tracking.today()
        if inbox.quota_day != today:
            inbox.quota_day, inbox.quota_used = today, 0
        allowed = min(len(new), max(0, daily_links() - inbox.quota_used)) if result.has_experience else 0
        batch, rest = new[:allowed], new[allowed:][:MAX_WAITING]
        inbox.quota_used += allowed
        inbox.pending = json.dumps(rest)
        if received:
            inbox.last_received_at = datetime.now(UTC)
            inbox.received_count += 1
            inbox.forwarding_code = inbox.forwarding_from = ""  # ya llegan alertas: el reenvío quedó confirmado
        for start in range(0, len(batch), discovery.MAX_BATCH):
            jobs.add(s, user_id, "alerta", {"urls": batch[start:start + discovery.MAX_BATCH]})
    if batch:
        jobs.new_job.set()
    result.queued, result.waiting = len(batch), len(rest)
    return result


def _waiting(inbox: AlertInbox) -> list[str]:
    try:
        urls = json.loads(inbox.pending or "[]")
    except json.JSONDecodeError:
        return []
    return [u for u in urls if isinstance(u, str)] if isinstance(urls, list) else []


def _drain_waiting(report: CheckReport) -> None:
    """Lo que esperaba cupo (p. ej. de ayer) entra a análisis aunque no lleguen correos nuevos."""
    with session_scope() as s:
        ids = list(s.scalars(select(AlertInbox.id).where(AlertInbox.pending.not_in(("", "[]")))))
    for inbox_id in ids:
        try:
            report.queued += _enqueue(inbox_id, [], received=False).queued
        except Exception:
            logger.exception("No se pudieron mandar a analizar las vacantes en espera")


def defer(username: str, urls: list[str]) -> None:
    """Devuelve a la espera vacantes que no se alcanzaron a analizar (p. ej. se acabó el cupo de IA)."""
    if not urls:
        return
    with session_scope() as s:
        inbox = s.scalar(select(AlertInbox).where(AlertInbox.user_id == _user_id(s, username)))
        if inbox is not None:
            inbox.pending = json.dumps(list(dict.fromkeys(urls + _waiting(inbox)))[:MAX_WAITING])


def _summary(portal: str, found: int, result: _Result) -> str:
    if not found:
        return f"{portal}: el correo no traía vacantes reconocibles."
    parts = []
    if result.queued:
        parts.append(f"{result.queued} {'nueva' if result.queued == 1 else 'nuevas'} en análisis")
    if result.repeated:
        parts.append(f"{result.repeated} ya {'estaba' if result.repeated == 1 else 'estaban'} en tu bandeja o postulaciones")
    if result.waiting and not result.has_experience:
        parts.append(f"{result.waiting} en espera: registra tu experiencia en Perfil para analizarlas")
    elif result.waiting:
        parts.append(f"{result.waiting} en espera por el tope diario de {daily_links()} (se analizan mañana)")
    return f"{portal}: " + ", ".join(parts) + "."
