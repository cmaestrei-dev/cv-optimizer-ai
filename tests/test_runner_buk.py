"""Buk semiautomático (autorizado por el dueño el 2026-11-27) contra un Buk falso con la estructura de los formularios reales
de Ceiba y Quipux: campos `attempt[ID][answer_…]`, radios con el texto de la opción como valor, CV que solo se sube al
enviar, «Enviar Respuesta» → «Enviar» → «Éxito», y el correo «Confirma tu correo». Sin red ni correo real."""

import json
import re
from datetime import UTC, datetime
from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from runner import __main__ as cli
from runner import buk_apply as buk
from runner import config as cfg

playwright = pytest.importorskip("playwright.sync_api")

FORM = ("https://linq.buk.co/recruiting/surveys/" + "a" * 40 + "/attempt_tokens/" + "b" * 40 + "/edit_attempt")
PAGE = """<html><head><title>Buk - Quipux</title></head><body>
<p>Postulando a Desarrollador Python | Medellín</p>
<form>
<div class="q"><label for="a1">Nombre*</label><input id="a1" name="attempt[1][answer_text]"></div>
<div class="q"><label for="a2">Primer Apellido*</label><input id="a2" name="attempt[2][answer_text]"></div>
<div class="q"><label for="a3">Segundo Apellido</label><input id="a3" name="attempt[3][answer_text]"></div>
<div class="q"><div>Tipo de documento*</div>
  <input type="radio" name="attempt[4][answer_text]" value="Tarjeta de identidad (TI)"><span>TI</span>
  <input type="radio" name="attempt[4][answer_text]" value="Cédula de ciudadanía (CC)"><span>CC</span></div>
<div class="q"><label for="a5">Numero de Documento*</label><input id="a5" name="attempt[5][answer_text]"></div>
<div class="q"><label for="a6">Celular*</label><input id="a6" name="attempt[6][answer_text]"></div>
<div class="q"><label for="a7">Email*</label><input id="a7" name="attempt[7][answer_text]" value="ya@lleno.com"></div>
<div class="q"><div>¿Cuenta con alguna discapacidad?*</div>
  <input type="radio" name="attempt[8][answer_text]" value="Si"><input type="radio" name="attempt[8][answer_text]" value="No"></div>
<div class="q"><label for="a9">Años de experiencia *</label><input id="a9" type="number" name="attempt[9][answer_text]"></div>
<div class="q"><label for="a10">Dirección</label><input id="a10" name="attempt[10][answer_text]"></div>
<div class="q"><label for="a11">CV*</label><input id="a11" type="file" name="attempt[11][answer_file]"><small>Formato PDF</small></div>
<div class="q"><label for="a12">Fecha de Nacimiento*</label><input id="a12" name="attempt[12][answer_text]" placeholder="dd-mm-yyyy"></div>
<button type="button" onclick="ask()">Enviar Respuesta</button>
</form>
<script>
function ask() {
  document.body.insertAdjacentHTML('beforeend', '<div role="dialog"><p>¿Enviar tu respuesta?</p><button onclick="send()">Enviar</button></div>');
}
async function send() {
  const data = {};
  for (const el of document.querySelectorAll('[name^="attempt["]')) {
    if (el.type === 'radio') { if (el.checked) data[el.name] = el.value; }
    else if (el.type === 'file') data[el.name] = el.files.length ? el.files[0].name : '';
    else data[el.name] = el.value;
  }
  await fetch('/submit', {method: 'POST', body: JSON.stringify(data)});
  document.body.innerHTML = '<h2>¡Éxito!</h2><p>Respuesta enviada</p>';
}
</script></body></html>"""


@pytest.fixture(scope="module")
def chromium():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Sin Chromium para Playwright: {e}")
        yield b
        b.close()


class FakeBuk:
    def __init__(self):
        self.posts = []

    def handle(self, route, request):
        if request.method == "POST":
            self.posts.append(json.loads(request.post_data))
            return route.fulfill(status=200, body="{}")
        if "/confirmar" in request.url or "url9191" in request.url:
            return route.fulfill(status=200, content_type="text/html", body=(
                "<script>location.href = 'https://linq.buk.co/confirmado'</script>" if "url9191" in request.url
                else "<p>Correo confirmado</p>"))
        if request.url.endswith("/confirmado"):
            return route.fulfill(status=200, content_type="text/html", body="<p>Correo confirmado</p>")
        return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=PAGE)


def open_page(chromium, fake):
    page = chromium.new_page()
    page.route("**/*", lambda route, request: route.abort())
    page.route(re.compile(r"https://[a-z0-9]+\.buk\.co/.*"), fake.handle)
    return page


CONTACT = {"full_name": "Camilo Maestre", "email": "camilo@example.com", "phone": "+57 305 000 0000",
           "city": "Cartagena de Indias", "linkedin_url": "https://www.linkedin.com/in/camilo"}
BANK = {"numero de cedula|numero de cc": "1234567890", "discapacidad": "No tengo discapacidad",
        "fecha de nacimiento": "01-01-2000"}


def run(chromium, fake, tmp_path, *, submit=True, bank=None):
    page = open_page(chromium, fake)
    cv = tmp_path / "Camilo_Maestre_Desarrollador_Python_Quipux.pdf"
    cv.write_bytes(b"%PDF-1.4")
    try:
        return buk.apply(page, FORM, cv, lambda qs: {q.label: "2" for q in qs if "experiencia" in q.label}, submit=submit,
                         contact=CONTACT, overrides=bank if bank is not None else BANK, bank=bank if bank is not None else BANK,
                         legal_name="Camilo Andres Maestre Iglesias")
    finally:
        page.close()


def test_fills_and_sends_the_form(chromium, tmp_path):
    fake = FakeBuk()
    result = run(chromium, fake, tmp_path)
    assert result.status == "enviada", result
    (sent,) = fake.posts
    get = lambda n: sent[f"attempt[{n}][answer_text]"]  # noqa: E731
    assert (get(1), get(2), get(3)) == ("Camilo Andres", "Maestre", "Iglesias")
    assert (get(4), get(5), get(6), get(7)) == ("Cédula de ciudadanía (CC)", "1234567890", "3050000000", "ya@lleno.com")
    assert (get(8), get(9), get(10), get(12)) == ("No", "2", "", "01-01-2000")  # la dirección opcional no se adivina
    assert sent["attempt[11][answer_file]"] == "Camilo_Maestre_Desarrollador_Python_Quipux.pdf"


def test_dry_run_and_missing_answers_never_send(chromium, tmp_path):
    fake = FakeBuk()
    assert run(chromium, fake, tmp_path, submit=False).status == "revisada" and fake.posts == []
    without = {k: v for k, v in BANK.items() if "fecha" not in k}
    skipped = run(chromium, fake, tmp_path, bank=without)
    assert skipped.status == "saltada" and skipped.unanswered == ["Fecha de Nacimiento"] and fake.posts == []


def message(*, host="linq", auth="mx.google.com; dkim=pass header.i=@buk.co; spf=pass; dmarc=pass header.from=buk.co",
            link="https://url9191.buk.co/ls/click?upn=abc", text="Confirmar correo"):
    msg = EmailMessage()
    msg["From"] = "Selección Quipux <noreply@buk.co>"
    msg["Subject"] = "Confirma tu correo para completar tu postulación"
    msg["Authentication-Results"] = auth
    msg.add_alternative(f'<p>Confirma tu correo.</p><a href="{link}">{text}</a><a href="https://url9191.buk.co/x"><img alt="Buk"></a>'
                        f"<p>Correo enviado a través de {host}.buk.co</p>", subtype="html")
    return msg


def test_only_buks_own_confirmation_is_trusted():
    assert buk.authenticated(message()) and buk.confirm_link(message(), "linq") == "https://url9191.buk.co/ls/click?upn=abc"
    assert buk.confirm_link(message(host="ceiba"), "linq") == ""            # otra empresa
    assert buk.confirm_link(message(link="https://evil.example/x"), "linq") == ""  # botón fuera de Buk
    assert buk.confirm_link(message(text="Darse de baja"), "linq") == ""
    forged = message(auth="evil.example; dkim=pass header.i=@buk.co")      # el primero no es el de Gmail
    assert not buk.authenticated(forged)
    assert not buk.authenticated(message(auth="mx.google.com; dkim=fail header.i=@buk.co; spf=softfail"))


def test_confirms_the_email(chromium, monkeypatch):
    monkeypatch.setattr(buk.time, "sleep", lambda s: None)
    page = open_page(chromium, FakeBuk())
    try:
        found = buk.confirm_by_email(page, "camilo@gmail.com", "x", "linq", datetime.now(UTC),
                                     finder=lambda *a: "https://url9191.buk.co/ls/click?upn=abc")
        assert found == "" and page.url == "https://linq.buk.co/confirmado"
        assert buk.confirm_by_email(page, "c@gmail.com", "x", "linq", datetime.now(UTC), wait_seconds=0,
                                    finder=lambda *a: "") == "no llegó el correo de confirmación de Buk"
    finally:
        page.close()


def test_telegram_queues_the_form_and_starts_the_sender(monkeypatch, tmp_path):
    from runner import telegram

    monkeypatch.setattr(buk, "QUEUE", tmp_path / "buk_cola.json")
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    started = []
    monkeypatch.setattr(telegram.subprocess, "Popen", lambda cmd, **k: started.append(cmd))
    assert "Recibido" in telegram.handle(f"/buk {FORM}", None, [])[0]
    assert started[0][-2:] == ["runner", "buk"] and buk.read_queue()[0]["form"] == FORM
    assert "ya está en cola" in telegram.handle(f"/buk {FORM}", None, [])[0] and len(started) == 1
    assert "enlace del formulario" in telegram.handle("/buk https://evil.example/edit_attempt", None, [])[0]


def test_the_form_finds_its_vacancy():
    apps = [{"id": 1, "url": "https://linq.buk.co/s/abc", "role": "Desarrollador Python", "status": "cv_generado"},
            {"id": 2, "url": "https://linq.buk.co/s/def", "role": "Analista de Datos", "status": "cv_generado"},
            {"id": 3, "url": "https://ceiba.buk.co/s/ghi", "role": "Desarrollador Python", "status": "cv_generado"}]
    api = SimpleNamespace(get=lambda path: apps, post=lambda path, body: pytest.fail("no debía crear otra"))
    form = buk.Form("linq", "Quipux", "Desarrollador Python Junior")
    assert cli._buk_app(api, form, "") == 1
    assert cli._buk_app(api, buk.Form("linq", "Quipux", "Contador"), "") is None  # nada parecido y sin oferta
    created = SimpleNamespace(get=lambda path: [], post=lambda path, body: {"id": 9})
    assert cli._buk_app(created, form, "https://linq.buk.co/s/xyz") == 9
