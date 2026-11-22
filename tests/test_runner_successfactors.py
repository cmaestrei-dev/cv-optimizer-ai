"""Postular en un portal SuccessFactors (Bancolombia) contra uno falso: la oferta, «Aplicar» → «Enviar candidatura
ahora», el formulario con las preguntas del puesto como las del real (radios propios, lista, áreas de texto,
declaración, currículum) y «Puestos solicitados (N)». Sin red ni cuenta real. Necesita Playwright y un Chromium."""

import json
import re
from urllib.parse import urlparse

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from runner import successfactors_apply as sf  # noqa: E402

OFFER = "https://empleo.grupobancolombia.com/bancolombia/job/Etipani-Ingenieroa-Software-Backend-COL/1451777800/"
PROFILE = "https://career8.successfactors.com/portalcareer?company=X&navBarLevel=MY_PROFILE"


def radio(qid: int, label: str, options: list[str]) -> str:
    opts = "".join(
        f'<span id="{qid + i + 1}:_radio" onclick="pick(\'{qid}\', {qid + i + 1})"><span id="{qid + i + 1}:_anchor" '
        f'role="radio" aria-checked="false" aria-labelledby="{qid + i + 1}:_radiolabel"></span>'
        f'<label id="{qid + i + 1}:_radiolabel" class="radioLabel">{o}</label></span>' for i, o in enumerate(options))
    return (f'<label id="{qid}:l" for="{qid}:" class="rcmFormQuestionLabel"><span class="requiredField">*</span>&nbsp;'
            f'{label}</label><div id="{qid}:" role="radiogroup" aria-labelledby="{qid}:l">{opts}</div>')


class FakeSF:
    def __init__(self, *, logged: bool = True):
        self.logged, self.applied, self.posted = logged, 1, []

    def _form(self) -> str:
        return f"""<html><body><a>Salir</a><span>Ampliar todas las secciones</span>
          <div>Mis documentos <span id="cv-name">CV_viejo.pdf</span>
            <span id="41:_attachIcon" onclick="document.getElementById('f').style.display='block'">✎</span>
            <input type="file" id="f" style="display:none"
                   onchange="document.getElementById('cv-name').innerText = this.files[0].name"></div>
          <div><h3>Información específica del puesto</h3>
            {radio(700, "¿Tienes algún pariente, cónyuge o persona con relación análoga que trabaje actualmente con Bancolombia?",
                   ["1 familiar", "Mas de 3 familiares", "No tengo familiares en Bancolombia"])}
            {radio(710, "¿Cómo te enteraste de esta vacante?",
                   ["LinkedIn: La encontré navegando en LinkedIn.", "Portal de empleo de Bancolombia: Apliqué directamente."])}
            {radio(720, "¿Tienes experiencia con Kubernetes?", ["Si.", "No."])}
            <label for="730:" class="rcmFormQuestionLabel"><span class="requiredField">*</span>&nbsp;¿Cuál es tu salario actual o último salario?</label>
            <textarea id="730:"></textarea>
            <label for="740:" class="rcmFormQuestionLabel"><span class="requiredField">*</span>&nbsp;¿Cuál es tu nivel de formación académica?</label>
            <select id="740:"><option>1-Bachiller</option><option>5-6 a 10 semestre carrera universitaria</option></select>
            <label for="750:" class="rcmFormQuestionLabel">¿Algo más que quieras contarnos?</label><textarea id="750:"></textarea>
          </div>
          <input type="text" name="disclaimerAcknowledge">
          <span id="apply" onclick="send()">Aplicar</span>
          <script>
            function pick(group, id) {{
              document.querySelectorAll('[id="' + group + ':"] [role=radio]').forEach(r => r.setAttribute('aria-checked', 'false'));
              document.getElementById(id + ':_anchor').setAttribute('aria-checked', 'true'); }}
            async function send() {{
              const radios = {{}}; document.querySelectorAll('[role=radiogroup]').forEach(g => {{
                const c = g.querySelector('[aria-checked=true]'); radios[g.id] = c ? document.getElementById(c.getAttribute('aria-labelledby')).innerText : ''; }});
              await fetch('/apply', {{method: 'POST', body: JSON.stringify({{radios, salario: document.getElementById('730:').value,
                formacion: document.getElementById('740:').value, firma: document.querySelector('[name=disclaimerAcknowledge]').value,
                cv: document.getElementById('cv-name').innerText}})}});
              document.body.insertAdjacentHTML('beforeend', '<p>Gracias por postularte</p>'); }}
          </script></body></html>"""

    def handle(self, route, request):
        url = urlparse(request.url)
        if url.path == "/apply":
            self.posted.append(json.loads(request.post_data))
            self.applied += 1
            return route.fulfill(status=200, content_type="application/json", body="{}")
        if "navBarLevel=MY_PROFILE" in request.url:
            body = f"<html><body><a>Salir</a> Puestos solicitados ({self.applied})</body></html>"
        elif url.path.startswith("/bancolombia/job/"):
            body = """<html><body><button onclick="document.getElementById('m').style.display='block'">Aplicar ▾</button>
              <div id="m" style="display:none"><a href="https://career8.successfactors.com/portalcareer?form=1">Enviar candidatura ahora</a></div></body></html>"""
        elif "form=1" in request.url:
            body = self._form() if self.logged else '<html><body><input type="password"></body></html>'
        else:
            body = "<html></html>"
        return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)


@pytest.fixture(scope="module")
def chromium():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Sin Chromium para Playwright: {e}")
        yield b
        b.close()


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(sf.time, "sleep", lambda s: None)


def run(chromium, fake, tmp_path, *, submit=True, answers=None):
    page = chromium.new_page()
    page.route("**/*", lambda route, request: route.abort())  # nada sale a la red
    page.route(re.compile(r"https://(empleo\.grupobancolombia\.com|career8\.successfactors\.com)/.*"), fake.handle)
    cv = tmp_path / "Camilo_Maestre_Backend_Junior.pdf"
    cv.write_bytes(b"%PDF-1.4")
    known = {"¿Tienes experiencia con Kubernetes?": "Si."} if answers is None else answers
    overrides = {"pariente, conyuge|relacion analoga": "No tengo familiares en Bancolombia",
                 "como te enteraste": "Portal de empleo de Bancolombia", "nivel de formacion academica": "5-6 a 10 semestre carrera universitaria",
                 "salario actual|ultimo salario": "2000000"}
    try:
        return sf.apply(page, OFFER, cv, lambda qs: {q.label: known[q.label] for q in qs if q.label in known}, submit=submit,
                        full_name="Camilo Andres Maestre Iglesias", overrides=overrides, profile_url=PROFILE)
    finally:
        page.close()


def test_applies_with_this_vacancys_cv_and_the_bank(chromium, tmp_path):
    fake = FakeSF()
    result = run(chromium, fake, tmp_path)
    assert result.status == "enviada" and "pasó de 1 a 2" in result.detail, result
    (sent,) = fake.posted
    assert sent["radios"] == {"700:": "No tengo familiares en Bancolombia",
                              "710:": "Portal de empleo de Bancolombia: Apliqué directamente.", "720:": "Si."}
    assert sent["salario"] == "2000000" and sent["formacion"] == "5-6 a 10 semestre carrera universitaria"
    assert sent["firma"] == "Camilo Andres Maestre Iglesias" and sent["cv"] == "Camilo_Maestre_Backend_Junior.pdf"


def test_dry_run_unanswered_and_no_session_never_send(chromium, tmp_path):
    fake = FakeSF()
    assert run(chromium, fake, tmp_path, submit=False).status == "revisada" and fake.posted == []
    skipped = run(chromium, fake, tmp_path, answers={})  # nadie sabe lo de Kubernetes: no se envía
    assert skipped.status == "saltada" and skipped.unanswered == ["¿Tienes experiencia con Kubernetes?"] and fake.posted == []
    assert run(chromium, FakeSF(logged=False), tmp_path).status == "sin_sesion"
