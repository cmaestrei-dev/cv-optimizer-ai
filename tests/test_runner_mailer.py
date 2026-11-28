"""Postular por correo cuando la vacante lo pide (autorizado por el dueño el 2026-11-26), con un Gmail falso: nada sale a
la red ni se usa una contraseña real."""

import dataclasses
import smtplib
from datetime import date, timedelta

import pytest

from runner import __main__ as cli
from runner import config as cfg
from runner import linkedin_posts as lp
from runner import mailer, telegram
from runner.api import Vacancy
from runner.state import State


class FakeSMTP:
    sent: list = []
    logins: list = []
    reject = False

    def __init__(self, host, port, context=None, timeout=None):
        assert (host, port, timeout) == ("smtp.gmail.com", 465, 30)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, secret):
        if FakeSMTP.reject:
            raise smtplib.SMTPAuthenticationError(535, b"bad")
        FakeSMTP.logins.append((user, secret))

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


class FakeApi:
    def __init__(self):
        self.posts = []

    def get(self, path):
        assert path == "/profile"
        return {"contact": {"full_name": "Camilo Maestre", "phone": "+57 300 000 0000", "email": "camilo@example.com",
                            "linkedin_url": "https://www.linkedin.com/in/camilo"}}

    def post(self, path, body=None):
        self.posts.append((path, body))
        if path.endswith("/cover"):
            return {"text": "Hola, me postulo a la vacante de Desarrollador Junior. Tengo experiencia con Python y React."}
        return {}


@pytest.fixture
def mail(monkeypatch, tmp_path):
    FakeSMTP.sent, FakeSMTP.logins, FakeSMTP.reject = [], [], False
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(mailer, "SECRET_FILE", tmp_path / "correo")
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    notices = []
    monkeypatch.setattr(telegram, "notify", lambda text: notices.append(text) or True)
    mailer.save_password("abcd efgh ijkl mnop".replace(" ", ""))
    cv = tmp_path / "Camilo_Maestre_Desarrollador.pdf"
    cv.write_bytes(b"%PDF-1.4 cv")
    conf = cfg.Config(api="http://127.0.0.1:9", token="t", mode="auto", mail_from="camilo@gmail.com", mail_cap=2)
    return conf, State(tmp_path / "estado.json"), cv, notices


VACANCY = Vacancy(9, True, "Desarrollador Junior", "Acme SAS", 80, [], "guardada")
TEXT = "Buscamos Desarrollador Junior. Envía tu hoja de vida a talento@acme.co con el asunto: Desarrollador Junior 2026."


def test_sends_the_cv_with_the_requested_subject_and_records_it(mail):
    conf, state, cv, notices = mail
    api = FakeApi()
    assert cli._apply_by_email(api, conf, state, VACANCY, ["talento@acme.co"], TEXT, cv, 31) == "talento@acme.co"
    (msg,) = FakeSMTP.sent
    assert FakeSMTP.logins == [("camilo@gmail.com", "abcdefghijklmnop")]
    assert (msg["To"], msg["Subject"], msg["From"]) == ("talento@acme.co", "Desarrollador Junior 2026",
                                                        "Camilo Maestre <camilo@gmail.com>")
    body = msg.get_body(("plain",)).get_content()
    assert body.startswith("Hola, me postulo a la vacante de Desarrollador Junior.")
    assert "Cordialmente,\nCamilo Maestre\n+57 300 000 0000\ncamilo@example.com" in body
    (attachment,) = list(msg.iter_attachments())
    assert attachment.get_filename() == cv.name and attachment.get_content() == b"%PDF-1.4 cv"
    assert ("/applications/9/sent", {"cv_id": 31, "platform": "Correo o referido"}) in api.posts
    assert ("/applications/9/notes", {"note": "Enviada por correo a talento@acme.co · asunto «Desarrollador Junior 2026»"}) in api.posts
    assert "Te postulé por correo: Desarrollador Junior — Acme SAS" in notices[0]
    saved = State(cfg.DATA_DIR / "estado.json")
    assert saved.today("correos") == 1 and saved.data["correos_enviados"] == {"talento@acme.co": date.today().isoformat()}
    assert saved.data["correos_vacantes"] == {"talento@acme.co|acme|desarrollador junior": date.today().isoformat()}


def test_one_email_per_vacancy_and_per_address_per_day(mail):
    # Decisión del dueño (2026-11-28): Perceptual publicó otra vacante con el mismo reclutador y la regla de 30 días
    # por dirección la mandó a Telegram. Ahora: nunca la misma vacante dos veces; otra sí, máximo una al día.
    conf, state, cv, _ = mail
    other = Vacancy(10, True, "Desarrollador Mobile", "Acme SAS", 70, [], "guardada")
    assert cli._apply_by_email(FakeApi(), conf, state, VACANCY, ["talento@acme.co"], TEXT, cv, 31)
    why: list[str] = []
    assert cli._apply_by_email(FakeApi(), conf, state, VACANCY, ["Talento@acme.co"], TEXT, cv, 31, why=why) == ""
    assert "misma vacante" in why[0]
    why.clear()
    assert cli._apply_by_email(FakeApi(), conf, state, other, ["talento@acme.co"], TEXT, cv, 32, why=why) == ""
    assert "hoy ya le escribí" in why[0]  # otra vacante, el mismo día: mañana sí
    state.data["correos_enviados"]["talento@acme.co"] = (date.today() - timedelta(days=1)).isoformat()
    assert cli._apply_by_email(FakeApi(), conf, state, other, ["talento@acme.co"], TEXT, cv, 32) == "talento@acme.co"
    state.data["correos_enviados"]["talento@acme.co"] = (date.today() - timedelta(days=90)).isoformat()
    assert cli._apply_by_email(FakeApi(), conf, state, VACANCY, ["talento@acme.co"], TEXT, cv, 31) == ""  # nunca la misma
    why.clear()
    assert cli._apply_by_email(FakeApi(), conf, state, VACANCY, ["otra@empresa.co"], TEXT, cv, 31, why=why) == ""
    assert "tope diario" in why[0] and len(FakeSMTP.sent) == 2  # tope de 2


def test_without_setup_in_test_mode_or_rejected_nothing_is_sent(mail):
    conf, state, cv, notices = mail
    assert cli._apply_by_email(FakeApi(), dataclasses.replace(conf, mode="prueba"), state, VACANCY, ["a@b.co"], TEXT, cv, 31) == ""
    assert cli._apply_by_email(FakeApi(), dataclasses.replace(conf, mail_from=""), state, VACANCY, ["a@b.co"], TEXT, cv, 31) == ""
    assert cli._apply_by_email(FakeApi(), conf, state, VACANCY, ["noreply@b.co"], TEXT, cv, 31) == ""
    FakeSMTP.reject = True
    api = FakeApi()
    assert cli._apply_by_email(api, conf, state, VACANCY, ["a@b.co"], TEXT, cv, 31) == ""
    assert FakeSMTP.sent == [] and notices == [] and state.today("correos") == 0
    assert not any(path.endswith("/sent") for path, _ in api.posts)
    mailer.SECRET_FILE.unlink()
    assert cli._apply_by_email(FakeApi(), conf, state, VACANCY, ["a@b.co"], TEXT, cv, 31) == ""


def test_subject_and_recipients():
    assert mailer.requested_subject("Envía tu CV con el asunto «Practicante TI 2027»") == "Practicante TI 2027"
    assert mailer.requested_subject('Asunto: "QA Junior".') == "QA Junior"
    assert mailer.requested_subject("Envía tu hoja de vida a rrhh@x.co") == ""
    assert mailer.recipients(["no-reply@x.co", "rrhh@x.co", "notificaciones@y.co"]) == ["rrhh@x.co"]


def test_a_post_that_asks_for_email_is_applied_by_email(mail, monkeypatch):
    conf, state, cv, _ = mail
    post = lp.Post("1", "Ana", TEXT)

    class Api(FakeApi):
        def add_vacancy(self, *, text, url, posted, images=()):
            return VACANCY

        def get(self, path):
            if path == "/applications/9":
                return {"vacancy_text": TEXT}
            return super().get(path)

        def make_cv(self, app_id):
            return {"id": 31, "filename": cv.name}

        def download_cv(self, cv_id, dest):
            return cv

    monkeypatch.setattr(cli, "_foreign", lambda api, conf, app_id: "")
    monkeypatch.setattr(telegram, "add_manual", lambda item: pytest.fail("no debía ir a Telegram como manual"))
    conf = dataclasses.replace(conf, min_scores={"linkedin": 50})
    assert cli._handle_post(Api(), conf, post, "Daniela te mencionó", state) == {"estado": "correo", "app": 9, "para": "talento@acme.co"}


def test_when_the_email_is_not_sent_telegram_says_why(mail, monkeypatch):
    conf, state, cv, _ = mail
    state.data["correos_enviados"] = {"talento@acme.co": date.today().isoformat()}  # hoy ya se le escribió por otra
    post = lp.Post("1", "Ana", TEXT)
    manual = []

    class Api(FakeApi):
        def add_vacancy(self, *, text, url, posted, images=()):
            return VACANCY

        def get(self, path):
            return {"vacancy_text": TEXT} if path == "/applications/9" else super().get(path)

        def make_cv(self, app_id):
            return {"id": 31, "filename": cv.name}

        def download_cv(self, cv_id, dest):
            return cv

    monkeypatch.setattr(cli, "_foreign", lambda api, conf, app_id: "")
    monkeypatch.setattr(telegram, "add_manual", lambda item: manual.append(item))
    conf = dataclasses.replace(conf, min_scores={"linkedin": 50})
    assert cli._handle_post(Api(), conf, post, "Daniela te mencionó", state)["estado"] == "manual"
    assert manual[0]["motivo"].startswith("no la envié por correo: hoy ya le escribí a talento@acme.co")
