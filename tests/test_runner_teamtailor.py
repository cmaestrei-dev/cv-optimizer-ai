"""Postular en un Teamtailor falso como el real (Periferia IT, 2026-11-22): preguntas de texto, de opciones (una en
desplegable que llena un campo oculto obligatorio), datos de contacto, el CV y el consentimiento. Sin red."""

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from runner import config as cfg  # noqa: E402
from runner import teamtailor_apply as tt  # noqa: E402
from runner import watch  # noqa: E402

OFFER = "https://jobs.periferiaitgroup.com/jobs/8777639-analista-soporte"
CONTACT = {"full_name": "Camilo Maestre", "email": "camilo@example.com", "phone": "+57 300 000 0000", "city": "Cartagena, Colombia"}


class FakeTeamtailor:
    def __init__(self):
        self.posted: list[dict] = []

    @staticmethod
    def _form() -> str:
        return """<html><body>
<form id="job-application-form" action="/jobs/8777639/applications" method="post">
 <div class="question" data-question-mandatory="true"><label for="q0">¿Dónde vives actualmente (ciudad y barrio)?<sup>*</sup></label>
   <input type="text" id="q0" name="candidate[answers_attributes][0][text]" required></div>
 <div class="question" data-question-mandatory="true"><fieldset><legend>¿ Cuál es tu formación académica?<sup>*</sup></legend>
   <input class="sr-only" id="hidden1" required>
   <button type="button" aria-haspopup="menu" aria-controls="menu1" onclick="document.getElementById('menu1').style.display='block'">Escoge una opción</button>
   <div id="menu1" role="menu" style="display:none">
     <button type="button" role="menuitemradio" onclick="pick(1, 'c1_1', 1)">Profesional con Tarjeta profesional (Vigente)</button>
     <button type="button" role="menuitemradio" onclick="pick(1, 'c1_2', 2)">Estudiante Universitario</button></div>
   <input type="radio" id="c1_1" name="candidate[answers_attributes][1][choice]" value="1" style="display:none"><label for="c1_1" style="display:none">Profesional con Tarjeta profesional (Vigente)</label>
   <input type="radio" id="c1_2" name="candidate[answers_attributes][1][choice]" value="2" style="display:none"><label for="c1_2" style="display:none">Estudiante Universitario</label>
 </fieldset></div>
 <div class="question" data-question-mandatory="true"><fieldset><legend>Nivel de ingles<sup>*</sup></legend>
   <input type="radio" id="c2_1" name="candidate[answers_attributes][2][choice]" value="A1" required><label for="c2_1">A1</label>
   <input type="radio" id="c2_2" name="candidate[answers_attributes][2][choice]" value="A2"><label for="c2_2">A2</label>
 </fieldset></div>
 <div class="question" data-question-mandatory="true"><label for="q4">¿Indícanos meses de experiencia tienes el rol?<sup>*</sup></label>
   <input type="number" id="q4" name="candidate[answers_attributes][4][number]" required></div>
 <div class="question" data-question-mandatory="false"><label for="q3">Cuéntanos algo más</label><textarea id="q3" name="candidate[answers_attributes][3][text]"></textarea></div>
 <input type="text" id="candidate_first_name" name="candidate[first_name]" required>
 <input type="text" id="candidate_last_name" name="candidate[last_name]" required>
 <input type="email" id="candidate_email" name="candidate[email]" required>
 <input type="tel" id="candidate_phone" name="candidate[phone]" required>
 <label for="candidate_location">Dirección* Obligatorio</label>
 <input type="text" id="candidate_location" name="candidate[location][query]" oninput="suggest(this)">
 <input type="hidden" id="loc_city" name="candidate[location][city]"><ul id="suggestions"></ul>
 <label for="candidate_resume_remote_url">Subir currículum* Obligatorio</label>
 <input type="file" id="candidate_resume_remote_url" onchange="document.getElementById('cv-name').innerText = this.files[0].name; this.value = ''"><span id="cv-name"></span>
 <input type="checkbox" id="candidate_consent_given" name="candidate[consent_given]" value="1" required>
 <input type="checkbox" id="candidate_consent_given_future_jobs" name="candidate[consent_given_future_jobs]" value="1">
 <input type="submit" name="commit" value="Enviar">
</form>
<script>
 function suggest(input) {  // como Teamtailor: la ubicación se elige entre sugerencias (ciudad, país)
   const ul = document.getElementById('suggestions'); ul.innerHTML = '';
   for (const place of ['Cartagena, Spain', 'Cartagena, Colombia']) {
     if (!place.toLowerCase().startsWith(input.value.toLowerCase())) continue;
     const li = document.createElement('li'); li.setAttribute('role', 'option'); li.innerText = place;
     li.onclick = () => { input.value = place; document.getElementById('loc_city').value = place.split(',')[0]; ul.innerHTML = ''; };
     ul.appendChild(li); } }
 function pick(q, id, value) { document.getElementById(id).checked = true; document.getElementById('hidden' + q).value = value;
   document.getElementById('menu' + q).style.display = 'none'; }
 document.getElementById('job-application-form').addEventListener('submit', async ev => {
   ev.preventDefault();
   const data = Object.fromEntries(new FormData(ev.target)); data.cv = document.getElementById('cv-name').innerText;
   await fetch('/submit', {method: 'POST', body: JSON.stringify(data)});
   document.body.innerHTML = '<h1>¡Gracias por tu postulación!</h1>'; });
</script></body></html>"""

    def handle(self, route, request):
        url = urlparse(request.url)
        if url.path == "/submit":
            self.posted.append(json.loads(request.post_data))
            return route.fulfill(status=200, content_type="application/json", body="{}")
        if url.path.endswith("/applications/new"):
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self._form())
        return route.fulfill(status=404, body="")


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
    monkeypatch.setattr(tt.time, "sleep", lambda s: None)


def run(chromium, fake, tmp_path, *, submit=True, known=None):
    page = chromium.new_page()
    page.route("**/*", lambda route, request: route.abort())  # nada sale a la red
    page.route(re.compile(r"https://jobs\.periferiaitgroup\.com/.*"), fake.handle)
    cv = tmp_path / "Camilo_Maestre_Analista_Soporte_Periferia_IT.pdf"
    cv.write_bytes(b"%PDF-1.4")
    known = {"¿Dónde vives actualmente (ciudad y barrio)?": "Cartagena, Manga",
             "¿Indícanos meses de experiencia tienes el rol?": "12 meses"} if known is None else known
    overrides = {"formacion academica": "Estudiante Universitario", "nivel de ingles": "A2"}
    try:
        return tt.apply(page, OFFER, cv, lambda qs: {q.label: known[q.label] for q in qs if q.label in known},
                        submit=submit, contact=CONTACT, overrides=overrides)
    finally:
        page.close()


def test_fills_everything_and_sends_with_this_vacancys_cv(chromium, tmp_path):
    fake = FakeTeamtailor()
    result = run(chromium, fake, tmp_path)
    assert result.status == "enviada" and "Gracias por tu postulación" in result.detail, result
    (sent,) = fake.posted
    assert sent["candidate[answers_attributes][0][text]"] == "Cartagena, Manga"
    assert sent["candidate[answers_attributes][1][choice]"] == "2"  # desplegable: Estudiante Universitario
    assert sent["candidate[answers_attributes][2][choice]"] == "A2"
    assert sent["candidate[answers_attributes][4][number]"] == "12"  # el campo numérico solo lleva el número
    assert (sent["candidate[first_name]"], sent["candidate[last_name]"], sent["candidate[email]"]) == ("Camilo", "Maestre", "camilo@example.com")
    assert sent["candidate[consent_given]"] == "1" and "candidate[consent_given_future_jobs]" not in sent  # solo el obligatorio
    assert sent["candidate[answers_attributes][3][text]"] == ""  # la opcional no se inventa
    assert sent["cv"] == "Camilo_Maestre_Analista_Soporte_Periferia_IT.pdf"
    assert sent["candidate[location][query]"] == "Cartagena, Colombia" and sent["candidate[location][city]"] == "Cartagena"


def test_dry_run_and_unanswered_questions_never_send(chromium, tmp_path):
    fake = FakeTeamtailor()
    assert run(chromium, fake, tmp_path, submit=False).status == "revisada" and fake.posted == []
    skipped = run(chromium, fake, tmp_path, known={"¿Indícanos meses de experiencia tienes el rol?": "Sí, tengo experiencia"})
    assert skipped.status == "saltada"  # nadie sabe dónde vive, y «Sí» no es un número: no se envía
    assert skipped.unanswered == ["¿Dónde vives actualmente (ciudad y barrio)?", "¿Indícanos meses de experiencia tienes el rol?"]
    assert fake.posted == []


def test_names_and_application_link():
    assert tt._split_name("Camilo Andres Maestre Iglesias") == ("Camilo Andres", "Maestre Iglesias")
    assert tt._split_name("Camilo Maestre") == ("Camilo", "Maestre")
    assert tt.application_url(OFFER + "?utm=x") == OFFER + "/applications/new"
    assert tt.application_url(OFFER + "/applications/new") == OFFER + "/applications/new"


def test_postular_is_allowed_on_teamtailor_without_login(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[[vigilar]]\nnombre = "Periferia IT"\nportal = "teamtailor"\nsitio = "https://periferiait.teamtailor.com"\n'
                    'pais = "Colombia"\npostular = true\n', encoding="utf-8")
    (site,) = watch.load_sites(path)
    assert site.apply and site.portal in watch.AUTO_APPLY
    path.write_text('[[vigilar]]\nnombre = "Bold"\nportal = "recruitee"\nsitio = "https://jobs.bold.co"\npais = "Colombia"\npostular = true\n',
                    encoding="utf-8")
    with pytest.raises(cfg.ConfigError, match="postular"):
        watch.load_sites(path)


def test_query_string_is_ignored_when_building_the_form_link():
    assert parse_qs(urlparse(tt.application_url(OFFER)).query) == {}


def test_a_required_location_without_a_city_is_not_sent(chromium, tmp_path, monkeypatch):
    fake = FakeTeamtailor()
    monkeypatch.setitem(CONTACT, "city", "")
    result = run(chromium, fake, tmp_path)
    assert result.status == "saltada" and "ubicación" in result.detail and fake.posted == []
