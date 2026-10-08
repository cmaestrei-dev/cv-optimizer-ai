"""Alertas de empleo por correo: la dirección de reenvío de la cuenta y la revisión del buzón de la app."""

import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException, status

from api.auth import CurrentAccount
from api.schemas import AlertsCheckOut, AlertsOut
from core.alerts import service as alerts
from core.alerts.mailbox import MailboxError
from core.jobs import service as jobs

logger = logging.getLogger(__name__)
router = APIRouter(tags=["alertas"])
internal = APIRouter(include_in_schema=False)

# Solo las alertas: de LinkedIn únicamente el remitente de empleos (sus otros correos son mensajes privados).
GMAIL_FILTER = "from:(jobalerts-noreply@linkedin.com OR computrabajo.com OR elempleo.com OR magneto365.com)"


def _out(username: str, state: alerts.AlertStatus) -> AlertsOut:
    return AlertsOut(
        enabled=state.enabled, address=state.address, forwarding_code=state.forwarding_code,
        forwarding_from=state.forwarding_from, last_received_at=state.last_received_at,
        received_count=state.received_count, last_summary=state.last_summary, waiting=state.waiting,
        ignored_recently=state.ignored_recently,
        analyzing=jobs.count_active(username, "alerta") if state.address else 0,
        gmail_filter=GMAIL_FILTER, daily_limit=alerts.daily_links(),
    )


@router.get("/alerts", response_model=AlertsOut)
def get_alerts(account: CurrentAccount) -> AlertsOut:
    return _out(account.username, alerts.status(account.username))


@router.post("/alerts", response_model=AlertsOut)
def activate(account: CurrentAccount) -> AlertsOut:
    """Crea la dirección de reenvío de la cuenta (si ya existe, la devuelve igual)."""
    return _out(account.username, alerts.activate(account.username))


@router.post("/alerts/rotate", response_model=AlertsOut)
def rotate(account: CurrentAccount) -> AlertsOut:
    """Dirección nueva: la anterior deja de recibir (hay que cambiarla también en Gmail)."""
    return _out(account.username, alerts.activate(account.username, rotate=True))


@router.post("/alerts/check", response_model=AlertsOut)
def check(account: CurrentAccount) -> AlertsOut:
    """Revisa el buzón ahora (como mucho una vez por minuto, para todas las cuentas) y devuelve el estado."""
    try:
        alerts.check()
    except MailboxError:
        logger.warning("No se pudo revisar el buzón de alertas", exc_info=True)
    return _out(account.username, alerts.status(account.username))


def cron_enabled() -> bool:
    return len(os.environ.get("ALERTS_CRON_TOKEN", "").strip()) >= 32


@internal.post("/internal/alerts/check", response_model=AlertsCheckOut)
def scheduled_check(x_cron_token: str = Header(default="")) -> AlertsCheckOut:
    """Revisión programada (Cloud Scheduler, cada mañana): la bandeja queda lista antes de abrirla."""
    expected = os.environ.get("ALERTS_CRON_TOKEN", "").strip()
    if not hmac.compare_digest(x_cron_token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    report = alerts.check(force=True)
    return AlertsCheckOut(checked=report.checked, messages=report.messages, alerts=report.alerts,
                          queued=report.queued, rejected=report.rejected)
