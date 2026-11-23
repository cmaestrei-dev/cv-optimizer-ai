"""Postular en un Gupy falso con los pasos del real (Stefanini, 2026-11-23): «Continuar», información adicional,
preguntas de la empresa y «Finalizar candidatura». Sin red ni cuenta."""

import json
import re

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from runner import gupy_apply as gupy  # noqa: E402

OFFER = "https://stefaninilatam.gupy.io/jobs/12857712"

PAGE = """<html><body><main id="app"></main><ul id="menu"></ul><script>
let step = 'intro';
const app = document.getElementById('app');
const state = {questions: QUESTIONS};
function render() {
  if (step === 'intro') app.innerHTML = '<p>Hola Camilo, ¿continuamos con tu postulación?</p><button onclick="go(\\'info\\')">Continuar</button>';
  if (step === 'info') app.innerHTML = `<h2>Información adicional</h2>
    <p>¿Alguien que trabaja en esta empresa te indicó para esta vacante?</p>
    <input type="radio" name="radioGroupIsIndicatedTitle" value="yes" id="i1"><label for="i1">Sí</label>
    <input type="radio" name="radioGroupIsIndicatedTitle" value="no" id="i2"><label for="i2">No</label>
    <p>¿Trabajas en la empresa Stefanini Latam?</p>
    <input type="radio" name="radioGroupIsCompanyEmployeeTitle" value="yes" id="e1"><label for="e1">Sí</label>
    <input type="radio" name="radioGroupIsCompanyEmployeeTitle" value="no" id="e2"><label for="e2">No</label>
    <label for="how">¿Dónde encontraste esta vacante?</label><input id="how" name="howDidYouHearAboutUs" oninput="menu(this)">
    <button onclick="saveInfo()">Guardar y continuar</button>`;
  if (step === 'intro-questions') app.innerHTML = '<p>Preguntas creadas por la empresa</p><button onclick="go(\\'questions\\')">Responder ahora</button>';
  if (step === 'questions') app.innerHTML = '<h1>Preguntas creadas por la empresa Stefanini Latam</h1>' + state.questions +
    '<button onclick="saveQuestions()">Guardar y continuar</button>';
  if (step === 'finish') app.innerHTML = '<p>Preséntate! (opcional)</p><button>Personalizar candidatura</button><button onclick="finish()">Finalizar candidatura</button>';
  if (step === 'done') app.innerHTML = '<h1>¡Candidatura finalizada!</h1>';
}
function go(s) { step = s; render(); }
function menu(input) {
  const ul = document.getElementById('menu'); ul.innerHTML = '';
  for (const o of ['LinkedIn', 'Sitio de la empresa']) { const li = document.createElement('li'); li.innerText = o;
    li.onclick = () => { input.value = o; ul.innerHTML = ''; }; ul.appendChild(li); } }
async function saveInfo() {
  const data = {indicated: document.querySelector('[name=radioGroupIsIndicatedTitle]:checked')?.value,
                employee: document.querySelector('[name=radioGroupIsCompanyEmployeeTitle]:checked')?.value,
                how: document.getElementById('how').value};
  await fetch('/api/info', {method: 'POST', body: JSON.stringify(data)}); go('intro-questions'); }
async function saveQuestions() {
  const data = {}; for (const e of app.querySelectorAll('input, textarea')) { if (e.type === 'radio') { if (e.checked) data[e.name] = e.value; } else data[e.name] = e.value; }
  await fetch('/api/questions', {method: 'POST', body: JSON.stringify(data)}); go('finish'); }
async function finish() { await fetch('/api/complete', {method: 'POST', body: '{}'}); go('done'); }
render();
</script></body></html>"""

QUESTIONS = """<fieldset><legend>¿Tienes disponibilidad para trabajar presencial en Bogotá?</legend>
<input type="radio" name="q1" value="si" id="q1a"><label for="q1a">Sí</label>
<input type="radio" name="q1" value="no" id="q1b"><label for="q1b">No</label></fieldset>
<div><p>¿Cuántos años de experiencia tienes en soporte técnico?</p><input type="number" id="q2" name="q2"></div>"""


class FakeGupy:
    def __init__(self, *, logged=True, questions=QUESTIONS, list_first=False):
        self.logged, self.questions, self.posts, self.list_first = logged, questions, [], list_first

    def handle(self, route, request):
        if request.method == "POST":
            self.posts.append((request.url.rsplit("/", 1)[-1], json.loads(request.post_data or "{}")))
            return route.fulfill(status=200, content_type="application/json", body="{}")
        if not self.logged:
            return route.fulfill(status=200, content_type="text/html", body='<html><body><input type="password"></body></html>')
        if self.list_first:  # como el real: la primera visita a una postulación nueva cae en «Mis candidaturas»
            self.list_first = False
            return route.fulfill(status=200, content_type="text/html", body="<html><body><h1>Mis candidaturas</h1></body></html>")
        body = PAGE.replace("QUESTIONS", json.dumps(self.questions))
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
    monkeypatch.setattr(gupy.time, "sleep", lambda s: None)


def run(chromium, fake, tmp_path, *, submit=True, known=None):
    page = chromium.new_page()
    page.route("**/*", lambda route, request: route.abort())
    page.route(re.compile(r"https://stefaninilatam\.gupy\.io/.*"), fake.handle)
    known = {"¿Cuántos años de experiencia tienes en soporte técnico?": "1"} if known is None else known
    try:
        return gupy.apply(page, OFFER, tmp_path / "cv.pdf", lambda qs: {q.label: known[q.label] for q in qs if q.label in known},
                          submit=submit, overrides={"disponibilidad para trabajar presencial": "Sí"})
    finally:
        page.close()


def test_goes_through_every_step_and_finishes(chromium, tmp_path):
    fake = FakeGupy()
    result = run(chromium, fake, tmp_path)
    assert result.status == "enviada" and "Candidatura finalizada" in result.detail, result
    assert [name for name, _ in fake.posts] == ["info", "questions", "complete"]
    assert fake.posts[0][1] == {"indicated": "no", "employee": "no", "how": "Sitio de la empresa"}
    assert fake.posts[1][1] == {"q1": "si", "q2": "1"}


def test_dry_run_unanswered_and_no_session_never_finish(chromium, tmp_path):
    fake = FakeGupy()
    assert run(chromium, fake, tmp_path, submit=False).status == "revisada"
    assert "complete" not in [name for name, _ in fake.posts] and "questions" not in [name for name, _ in fake.posts]
    fake = FakeGupy()
    skipped = run(chromium, fake, tmp_path, known={})  # nadie sabe los años: no se guarda nada (no se puede editar luego)
    assert skipped.status == "saltada" and skipped.unanswered == ["¿Cuántos años de experiencia tienes en soporte técnico?"]
    assert [name for name, _ in fake.posts] == ["info"]
    assert run(chromium, FakeGupy(logged=False), tmp_path).status == "sin_sesion"


def test_a_company_without_questions_still_finishes(chromium, tmp_path):
    # Caso real (Stefanini): su servicio de preguntas respondió 404 y la página quedó vacía.
    fake = FakeGupy(questions="")
    assert run(chromium, fake, tmp_path).status == "enviada"
    assert [name for name, _ in fake.posts] == ["info", "questions", "complete"]


def test_apply_link():
    assert gupy.apply_url(OFFER) == "https://stefaninilatam.gupy.io/candidates/jobs/12857712/apply?jobBoardSource=gupy_public_page"
    with pytest.raises(ValueError):
        gupy.apply_url("https://stefaninilatam.gupy.io/")


def test_a_first_visit_that_lands_on_the_application_list_is_retried(chromium, tmp_path):
    fake = FakeGupy(list_first=True)
    assert run(chromium, fake, tmp_path).status == "enviada"
