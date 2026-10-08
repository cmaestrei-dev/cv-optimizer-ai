"""Alertas de empleo por correo → bandeja. Correos sintéticos: ninguna dirección ni vacante real."""

from contextlib import contextmanager
from email.message import EmailMessage

import pytest

from core.alerts import parsing
from core.alerts import service as alerts
from core.db import session_scope
from core.jobs import service as jobs
from core.jobs.models import Job
from core.profile import service as profiles
from core.tracking import service as tracking
from tests.test_api_engine import ana  # noqa: F401  (fixture: cuenta con perfil e IA de prueba)

MAILBOX = "buzon.prueba@gmail.com"
TOKEN = "a1b2c3d4e5f6a1b2c3d4e5f6"
LINKEDIN_JOB = "https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=x&refId=y&otpToken=SECRETO&trk=eml"
COMPUTRABAJO_JOB = ("https://co.computrabajo.com/ofertas-de-trabajo/"
                    "oferta-de-trabajo-de-auxiliar-administrativo-en-bogota-dc-0DFEA7F8A3BFDC2361373E686DCF3405?utm_source=alerta")
GOOD_AUTH = "mx.google.com; dkim=pass header.i=@linkedin.com header.s=s1 header.b=abc; spf=pass smtp.mailfrom=x; dmarc=pass (p=REJECT) header.from=linkedin.com"


def _email(*, sender="LinkedIn <jobalerts-noreply@linkedin.com>", to=None, auth=(GOOD_AUTH,), subject="Nuevos empleos",
           links=(LINKEDIN_JOB,), html=True) -> bytes:
    msg = EmailMessage()
    msg["Delivered-To"] = to or f"buzon.prueba+{TOKEN}@gmail.com"
    for value in auth:  # el primero es el de nuestro servidor; los demás, de más abajo
        msg["Authentication-Results"] = value
    msg["From"] = sender
    msg["To"] = "persona@example.com"
    msg["Subject"] = subject
    cards = "".join(f'<a href="{u.replace("&", "&amp;")}">Auxiliar administrativo · Empresa {i}</a>'
                    for i, u in enumerate(links))
    footer = ('<a href="https://www.linkedin.com/comm/jobs/alerts?otpToken=SECRETO">Administrar alertas</a>'
              '<a href="https://www.linkedin.com/e/v2?e=unsub&otpToken=SECRETO">Darse de baja</a>')
    if html:
        msg.set_content("Versión de texto")
        msg.add_alternative(f"<html><body>{cards}{footer}</body></html>", subtype="html")
    else:
        msg.set_content("\n".join(links))
    return bytes(msg)


class TestParsing:
    def test_linkedin_alert_gives_clean_job_links(self):
        parsed = parsing.parse(_email(links=(LINKEDIN_JOB, LINKEDIN_JOB.replace("refId=y", "refId=z"))), MAILBOX)
        assert (parsed.kind, parsed.token, parsed.portal) == ("alerta", TOKEN, "LinkedIn")
        assert [link.url for link in parsed.links] == ["https://www.linkedin.com/jobs/view/4012345678"]
        assert parsed.links[0].title == "Auxiliar administrativo · Empresa 0"
        assert "SECRETO" not in repr(parsed)  # los tokens de inicio de sesión nunca salen del correo

    def test_every_portal_pattern(self):
        assert parsing.job_url(COMPUTRABAJO_JOB) == COMPUTRABAJO_JOB.split("?")[0]
        mx = COMPUTRABAJO_JOB.replace("co.computrabajo", "mx.computrabajo")
        assert parsing.job_url(mx) == mx.split("?")[0]  # el país está en el host
        assert parsing.job_url("https://www.elempleo.com/co/ofertas-trabajo/auxiliar-contable-1886778090?x=1") == \
            "https://www.elempleo.com/co/ofertas-trabajo/auxiliar-contable-1886778090"
        assert parsing.job_url("https://www.magneto365.com/co/empleos/auxiliar-de-bodega-1093889") == \
            "https://www.magneto365.com/co/empleos/auxiliar-de-bodega-1093889"
        for url in ("https://www.linkedin.com/jobs/search?keywords=x", "https://co.computrabajo.com/trabajo-de-auxiliar",
                    "https://linkedin.com.evil.example/jobs/view/4012345678", "javascript:alert(1)",
                    "https://www.linkedin.com/e/v2?e=unsub", "http://[::1"):
            assert parsing.job_url(url) is None, url

    def test_plain_text_alert(self):
        parsed = parsing.parse(_email(links=(LINKEDIN_JOB,), html=False), MAILBOX)
        assert [link.url for link in parsed.links] == ["https://www.linkedin.com/jobs/view/4012345678"]

    def test_dmarc_alignment_is_enough(self):
        auth = ("mx.google.com; dkim=pass header.i=@sendgrid.net; dmarc=pass (p=NONE) header.from=computrabajo.com",)
        parsed = parsing.parse(_email(sender="Computrabajo <alertas@computrabajo.com>", auth=auth,
                                      links=(COMPUTRABAJO_JOB,)), MAILBOX)
        assert (parsed.kind, parsed.portal, len(parsed.links)) == ("alerta", "Computrabajo", 1)

    @pytest.mark.parametrize("kwargs, reason", [
        ({"auth": ("mx.google.com; dkim=fail header.i=@linkedin.com; dmarc=fail header.from=linkedin.com",
                   GOOD_AUTH)}, "DKIM"),  # el bueno está más abajo: lo pudo escribir cualquiera
        ({"auth": ("otro.servidor.com; " + GOOD_AUTH.split("; ", 1)[1],)}, "DKIM"),
        ({"auth": ()}, "DKIM"),
        ({"auth": ("mx.google.com; dkim=pass header.i=@sendgrid.net; dmarc=fail header.from=linkedin.com",)}, "DKIM"),
        ({"sender": "Alguien <alguien@gmail.com>"}, "portal"),
        ({"sender": "LinkedIn <messages-noreply@linkedin.com>"}, "no es de empleos"),
        ({"to": "otro.buzon+a1b2c3d4e5f6a1b2c3d4e5f6@gmail.com"}, "código"),
        ({"to": "buzon.prueba@gmail.com"}, "código"),
        # Datos que escribe el remitente (su MAIL FROM, comentarios, la parte local de header.i) no cuentan
        ({"auth": ("mx.google.com; spf=fail smtp.mailfrom=dmarc=pass.header.from=linkedin.com@evil.example; "
                   "dmarc=fail header.from=linkedin.com",)}, "DKIM"),
        ({"auth": ("mx.google.com; spf=softfail (google.com: dkim=pass header.d=linkedin.com) smtp.mailfrom=x@evil.example; "
                   "dmarc=fail header.from=linkedin.com",)}, "DKIM"),
        ({"auth": ("mx.google.com; dkim=pass header.i=linkedin.com@evil.example; dmarc=fail header.from=linkedin.com",)}, "DKIM"),
    ])
    def test_rejected(self, kwargs, reason):
        parsed = parsing.parse(_email(**kwargs), MAILBOX)
        assert parsed.kind == "rechazado" and reason in parsed.reason and not parsed.links

    def test_gmail_forwarding_confirmation(self):
        auth = ("mx.google.com; dkim=pass header.i=@google.com; dmarc=pass header.from=google.com",)
        raw = _email(sender="Equipo de Gmail <forwarding-noreply@google.com>", auth=auth, links=(),
                     subject="(#123456789) Confirmación de reenvío de Gmail: recibir correo de Persona.X@gmail.com")
        parsed = parsing.parse(raw, MAILBOX)
        assert (parsed.kind, parsed.forwarding_code, parsed.forwarding_from) == ("confirmacion", "123456789", "persona.x@gmail.com")
        fake = parsing.parse(_email(sender="Gmail <forwarding-noreply@google.com>", links=(),
                                    subject="(#123456789) Gmail Forwarding Confirmation"), MAILBOX)
        assert fake.kind == "rechazado"  # sin DKIM de Google
        shared = parsing.parse(_email(sender="Google Docs <drive-shares-noreply@google.com>", auth=auth, links=(),
                                      subject="(#123456789) te compartió un documento"), MAILBOX)
        assert shared.kind == "rechazado"  # otro remitente de Google no es una confirmación de reenvío


class FakeMailbox:
    def __init__(self, messages: list[bytes]):
        self.messages = dict(enumerate(messages))
        self.discarded: list[int] = []

    @contextmanager
    def open(self):
        yield self

    def fetch(self, limit):
        yield from list(self.messages.items())[:limit]

    def discard(self, uid):
        self.discarded.append(uid)
        del self.messages[uid]

    def empty_trash(self):
        self.trash_emptied = True


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(profiles, "_ready", False)
    profiles.ensure_ready()


@pytest.fixture
def mailbox_env(ready, monkeypatch):
    monkeypatch.setenv("ALERTS_MAILBOX", MAILBOX)
    monkeypatch.setenv("ALERTS_MAILBOX_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setattr(alerts, "_last_check", float("-inf"))


def _user(name="ana", *, experience=True) -> str:
    profiles.create_user(name)
    if experience:
        profiles.add_experience(name, role="Auxiliar Administrativa", achievements=["Facturé 180 facturas al mes"])
    return name


def _activate_only() -> None:
    """Deja el token de prueba en la única cuenta activada (los correos sintéticos van a esa dirección)."""
    from core.alerts.models import AlertInbox

    with session_scope() as s:
        s.query(AlertInbox).one().token = TOKEN


def _activate(name: str) -> str:
    alerts.activate(name)
    _activate_only()
    return name


def _alert_jobs() -> list[dict]:
    import json

    with session_scope() as s:
        return [json.loads(j.payload) for j in s.query(Job).filter(Job.kind == "alerta").order_by(Job.id)]


class TestService:
    def test_disabled_without_mailbox(self, ready, monkeypatch):
        monkeypatch.delenv("ALERTS_MAILBOX", raising=False)
        _user()
        assert alerts.status("ana").enabled is False
        assert alerts.check().checked is False

    def test_activate_and_rotate(self, mailbox_env):
        _user()
        first = alerts.activate("ana")
        assert first.address.startswith("buzon.prueba+") and first.address.endswith("@gmail.com")
        assert alerts.activate("ana").address == first.address  # idempotente
        assert alerts.activate("ana", rotate=True).address != first.address

    def test_alert_goes_to_the_inbox_queue(self, mailbox_env):
        _activate(_user())
        tracking.create_application("ana", role="Ya la tenía", url=COMPUTRABAJO_JOB.split("?")[0])
        for _ in range(3):  # trabajos de la persona en curso: las alertas no fallan por eso
            jobs.enqueue("ana", "cv", {"application_id": 0})
        box = FakeMailbox([_email(links=(LINKEDIN_JOB,)),
                           _email(sender="Computrabajo <alertas@computrabajo.com>", links=(COMPUTRABAJO_JOB,),
                                  auth=("mx.google.com; dkim=pass header.d=computrabajo.com",)),
                           _email(sender="Alguien <alguien@gmail.com>")])
        report = alerts.check(opener=box.open)
        assert (report.messages, report.alerts, report.queued, report.rejected) == (3, 2, 1, 1)
        assert box.messages == {} and box.trash_emptied  # todo se borra, también lo rechazado
        assert _alert_jobs() == [{"urls": ["https://www.linkedin.com/jobs/view/4012345678"]}]
        state = alerts.status("ana")
        assert state.received_count == 2 and "ya estaba" in state.last_summary

    def test_daily_cap_and_batches(self, mailbox_env, monkeypatch):
        monkeypatch.setenv("ALERTS_DAILY_LINKS", "12")
        _activate(_user())
        links = tuple(f"https://www.linkedin.com/comm/jobs/view/40123456{i:02d}/?otpToken=x" for i in range(15))
        report = alerts.check(opener=FakeMailbox([_email(links=links)]).open)
        assert report.queued == 12 and [len(p["urls"]) for p in _alert_jobs()] == [10, 2]
        assert "3 en espera por el tope diario de 12" in alerts.status("ana").last_summary
        alerts.check(force=True, opener=FakeMailbox([_email(links=(LINKEDIN_JOB,) + links[:2])]).open)
        state = alerts.status("ana")
        assert len(_alert_jobs()) == 2 and state.waiting == 4  # tope agotado; las repetidas no se cuentan dos veces
        assert "2 ya estaban" in state.last_summary
        monkeypatch.setattr(tracking, "today", lambda: tracking.date(2099, 1, 1))  # otro día: entra lo que esperaba
        assert alerts.check(force=True, opener=FakeMailbox([]).open).queued == 4
        assert alerts.status("ana").waiting == 0

    def test_needs_experience(self, mailbox_env):
        _activate(_user(experience=False))
        alerts.check(opener=FakeMailbox([_email()]).open)
        assert _alert_jobs() == [] and "registra tu experiencia" in alerts.status("ana").last_summary
        assert alerts.status("ana").waiting == 1
        profiles.add_experience("ana", role="Auxiliar", achievements=["Archivé"])
        alerts.check(force=True, opener=FakeMailbox([]).open)
        assert len(_alert_jobs()) == 1 and alerts.status("ana").waiting == 0

    def test_forwarding_code_shown_until_alerts_arrive(self, mailbox_env):
        _activate(_user())
        confirmation = _email(sender="Gmail <forwarding-noreply@google.com>", links=(),
                              auth=("mx.google.com; dkim=pass header.i=@google.com",),
                              subject="(#987654321) Gmail Forwarding Confirmation - Receive Mail from ana@example.com")
        alerts.check(opener=FakeMailbox([confirmation]).open)
        assert (alerts.status("ana").forwarding_code, alerts.status("ana").forwarding_from) == ("987654321", "ana@example.com")
        alerts.check(force=True, opener=FakeMailbox([_email()]).open)
        assert alerts.status("ana").forwarding_code == ""

    def test_old_address_stops_working(self, mailbox_env):
        _activate(_user())
        alerts.activate("ana", rotate=True)
        report = alerts.check(opener=FakeMailbox([_email()]).open)
        assert report.rejected == 1 and _alert_jobs() == []

    def test_unreadable_email_does_not_block_the_mailbox(self, mailbox_env, monkeypatch):
        _activate(_user())
        monkeypatch.setattr(parsing, "parse", lambda raw, mailbox: 1 / 0)
        box = FakeMailbox([b"basura"])
        assert alerts.check(opener=box.open).rejected == 1 and box.messages == {}

    def test_failing_email_stays_and_is_dropped_after_retries(self, mailbox_env, monkeypatch):
        _activate(_user())
        real = alerts._handle
        monkeypatch.setattr(alerts, "_failures", {})
        monkeypatch.setattr(alerts, "_handle", lambda parsed, report: (_ for _ in ()).throw(RuntimeError("base caída"))
                            if parsed.links and parsed.links[0].url.endswith("4012345678") else real(parsed, report))
        other = _email(links=("https://www.linkedin.com/jobs/view/4099999999",))
        box = FakeMailbox([_email(), other])
        alerts.check(opener=box.open)
        assert list(box.messages) == [0] and len(_alert_jobs()) == 1  # el siguiente se procesó igual
        alerts.check(force=True, opener=box.open)
        assert list(box.messages) == [0]
        alerts.check(force=True, opener=box.open)
        assert box.messages == {}  # tercer intento: se descarta

    def test_link_keeps_the_alert_address(self, client, mailbox_env, monkeypatch):
        from api.routers import profile as profile_router
        from models import UserProfile
        from tests.test_api import _h

        monkeypatch.setattr(profile_router, "_LINK_ATTEMPTS", {})
        monkeypatch.setattr("api.routers.profile.time.sleep", lambda s: None)
        legacy = UserProfile(username="dianita")
        legacy.set_password("clave-de-dianita")
        profiles.create_user("dianita", password_hash=legacy.password_hash, salt=legacy.salt)
        h = _h("google-diana")
        address = client.post("/alerts", headers=h).json()["address"]
        r = client.post("/me/link-legacy", headers=h, json={"username": "dianita", "password": "clave-de-dianita"})
        assert r.status_code == 200 and client.get("/alerts", headers=h).json()["address"] == address

    def test_quota_exhausted_mid_batch_goes_back_to_waiting(self, ana, mailbox_env, monkeypatch):  # noqa: F811
        from core.jobs import worker
        from core.usage import QuotaExceededError

        client, h, fake = ana
        client.post("/alerts", headers=h)
        _activate_only()
        links = ("https://www.linkedin.com/jobs/view/4011111111", "https://www.linkedin.com/jobs/view/4022222222")
        alerts.check(opener=FakeMailbox([_email(links=links)]).open)
        fake.fail_with = QuotaExceededError("Llegaste al límite diario de uso de la IA.")
        assert worker.run_once()
        assert client.get("/alerts", headers=h).json()["waiting"] == 2

    def test_alert_jobs_do_not_block_the_person(self, mailbox_env):
        _activate(_user())
        links = tuple(f"https://www.linkedin.com/comm/jobs/view/40123456{i:02d}/" for i in range(35))
        alerts.check(opener=FakeMailbox([_email(links=links[:30]), _email(links=links[30:])]).open)
        assert len(_alert_jobs()) == 4
        for _ in range(3):  # la persona sigue pudiendo pedir sus trabajos
            jobs.enqueue("ana", "cv", {"application_id": 0})
        assert jobs.claim().kind == "cv"  # y van antes que las alertas

    def test_checks_at_most_once_a_minute(self, mailbox_env):
        _user()
        assert alerts.check(opener=FakeMailbox([]).open).checked is True
        assert alerts.check(opener=FakeMailbox([]).open).checked is False
        assert alerts.check(force=True, opener=FakeMailbox([]).open).checked is True


class TestAPI:
    def test_flow(self, client, mailbox_env, monkeypatch):
        from tests.test_api import _h

        h = _h("ana")
        assert client.get("/alerts", headers=h).json()["address"] == ""
        out = client.post("/alerts", headers=h).json()
        assert out["enabled"] and out["address"].startswith("buzon.prueba+") and "jobalerts-noreply" in out["gmail_filter"]
        box = FakeMailbox([])
        monkeypatch.setattr(alerts, "open_mailbox", lambda address, password, host: box.open())
        assert client.post("/alerts/check", headers=h).json()["address"] == out["address"]
        assert client.post("/alerts/rotate", headers=h).json()["address"] != out["address"]

    def test_alert_ends_analyzed_in_the_inbox(self, ana, mailbox_env, monkeypatch):  # noqa: F811
        from core.jobs import worker

        client, h, fake = ana
        client.post("/alerts", headers=h)
        _activate_only()
        monkeypatch.setattr(alerts, "open_mailbox", lambda address, password, host: FakeMailbox([_email()]).open())
        assert client.post("/alerts/check", headers=h).json()["analyzing"] == 1  # lotes de alertas, no los pegados
        assert worker.run_once()
        inbox = client.get("/applications?view=bandeja", headers=h).json()
        assert [(a["url"], a["status"]) for a in inbox] == [("https://www.linkedin.com/jobs/view/4012345678", "por_revisar")]
        assert inbox[0]["match_score"] is not None and client.get("/alerts", headers=h).json()["analyzing"] == 0

    def test_disabled_server(self, client):
        from tests.test_api import _h

        assert client.get("/alerts", headers=_h("ana")).json()["enabled"] is False
        assert client.post("/alerts", headers=_h("ana")).status_code == 422

    def test_scheduled_check_needs_its_token(self, monkeypatch, mailbox_env):
        from fastapi.testclient import TestClient

        from api.main import create_app

        monkeypatch.setenv("API_INPROCESS_WORKER", "0")
        monkeypatch.setenv("AUTH_DEV_SECRET", "x" * 40)
        with TestClient(create_app()) as c:  # sin ALERTS_CRON_TOKEN la ruta no existe
            assert c.post("/internal/alerts/check", headers={"X-Cron-Token": ""}).status_code in (404, 405)
        monkeypatch.setenv("ALERTS_CRON_TOKEN", "t" * 40)
        monkeypatch.setattr(alerts, "open_mailbox", lambda address, password, host: FakeMailbox([]).open())
        with TestClient(create_app()) as c:
            assert c.post("/internal/alerts/check", headers={"X-Cron-Token": "malo"}).status_code == 404
            r = c.post("/internal/alerts/check", headers={"X-Cron-Token": "t" * 40})
            assert r.status_code == 200 and r.json()["checked"] is True
