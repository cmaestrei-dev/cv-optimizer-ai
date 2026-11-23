"""Postular en un AIRA falso como el de Falabella (2026-11-23): el formulario Vue con el CV que sube su componente,
la expectativa salarial, los años en deslizadores y las dos casillas que vienen marcadas. Sin red ni cuenta."""

import json
import re

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from runner import aira_apply as aira  # noqa: E402

OFFER = "https://falabella.airavirtual.com/postula/EDUCkJCruw7wrgHJjoWa?logged_action=apply&register=true"

FORM = """<html><body><div id="form">
 <div id="filewrap"><input type="file" id="cv" style="display:none"><span>resume.pdf</span></div>
 <label>Expectativa salarial (bruto mensual pesos COP)</label><input type="text" placeholder="Ej: 1.000.000" id="salary" value="3.000.000">
 <p>Años de experiencia en área Tecnología e Informática</p>
 <div id="s1">RADIOS</div>
 <label><input type="checkbox" id="save" checked> Guardar hoja de vida en mi perfil</label>
 <label><input type="checkbox" id="alerts" checked> Recibir alertas de empleo de esta empresa</label>
 <a id="send" onclick="send()">ENVIAR POSTULACIÓN</a></div>
<script>
 const formVm = {$options: {methods: {uploadCv() {}}}, $set(o, k, v) { o[k] = v; },
   general_info_group: {SALARY: {answer: '3000000'}, RESUME_SOURCE: {answer: 'PROFILE'}},
   specific_questions_groups: {work_experience: [{id: 1, type: 'slider', text: 'Años de experiencia en área Tecnología e Informática',
                                                   answer: null, data: {param_validation: 'required|max:200'}}]}};
 document.getElementById('form').__vue__ = formVm;
 document.getElementById('filewrap').__vue__ = {$options: {name: 'FileWithPreview'}, $parent: formVm, async changedFile() {
   const f = document.getElementById('cv').files[0];
   await fetch('/applicant-api/v1/applications/1/test/1/step/1/save_answers', {method: 'POST', body: JSON.stringify({cv: f.name})});
   formVm.general_info_group.RESUME_SOURCE.answer = 'UPLOADED'; }};
 document.getElementById('s1').__vue__ = {$options: {name: 'Slider'},
   handleChangeRadiosSlider(e) { formVm.specific_questions_groups.work_experience[0].answer = e[0].value; }};
 async function send() {
   const missing = !document.getElementById('salary').value || formVm.specific_questions_groups.work_experience[0].answer === null;
   if (missing) { document.body.insertAdjacentHTML('beforeend', '<p>Campo requerido</p>'); return; }
   await fetch('/applicant-api/v1/applications/1/test/1/step/2/save_answers', {method: 'POST', body: JSON.stringify({
     salary: document.getElementById('salary').value, years: formVm.specific_questions_groups.work_experience[0].answer,
     save_cv: document.getElementById('save').checked, alerts: document.getElementById('alerts').checked})});
   document.body.innerHTML = '<h1>Estado postulación</h1><p>Pruebas Personalidad (D32) 15 minutos Pendiente COMPLETAR</p>'; }
</script></body></html>""".replace("RADIOS", "".join(f'<input type="radio" name="q_1" value="{v}">' for v in range(6)))


class FakeAira:
    def __init__(self, *, logged=True, applied=False):
        self.logged, self.applied, self.posts = logged, applied, []

    def handle(self, route, request):
        if request.method == "POST":
            self.posts.append(json.loads(request.post_data))
            return route.fulfill(status=200, content_type="application/json", body="{}")
        if not self.logged:
            return route.fulfill(status=200, content_type="text/html",
                                 body='<html><body>Registro candidato <input type="password"></body></html>')
        if self.applied:
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body="<html><body>Estado postulación Pruebas</body></html>")
        return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=FORM)


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
    monkeypatch.setattr(aira.time, "sleep", lambda s: None)


def run(chromium, fake, tmp_path, *, submit=True, known=None):
    page = chromium.new_page()
    page.route("**/*", lambda route, request: route.abort())
    page.route(re.compile(r"https://falabella\.airavirtual\.com/.*"), fake.handle)
    cv = tmp_path / "Camilo_Maestre_Practicante_Area_de_Sistemas.pdf"
    cv.write_bytes(b"%PDF-1.4")
    known = {"Años de experiencia en área Tecnología e Informática": "1",
             "Expectativa salarial (bruto mensual pesos COP)": "3000000"} if known is None else known
    try:
        return aira.apply(page, OFFER, cv, lambda qs: {q.label: known[q.label] for q in qs if q.label in known}, submit=submit)
    finally:
        page.close()


def test_uploads_this_vacancys_cv_answers_and_sends(chromium, tmp_path):
    fake = FakeAira()
    result = run(chromium, fake, tmp_path)
    assert result.status == "enviada" and "pruebas" in result.follow_up, result
    upload, sent = fake.posts
    assert upload == {"cv": "Camilo_Maestre_Practicante_Area_de_Sistemas.pdf"}
    assert sent == {"salary": "3000000", "years": "1", "save_cv": False, "alerts": False}  # sin guardar el CV ni alertas


def test_an_internship_without_a_figure_asks_for_the_usual_stipend(chromium, tmp_path):
    fake = FakeAira()
    assert run(chromium, fake, tmp_path, known={"Años de experiencia en área Tecnología e Informática": "1"}).status == "enviada"
    assert fake.posts[-1]["salary"] == str(aira.INTERNSHIP_SALARY)


def test_dry_run_unanswered_no_session_and_already_applied(chromium, tmp_path):
    fake = FakeAira()
    assert run(chromium, fake, tmp_path, submit=False).status == "revisada" and len(fake.posts) == 1  # solo el CV
    skipped = run(chromium, FakeAira(), tmp_path, known={})
    assert skipped.status == "saltada" and skipped.unanswered == ["Años de experiencia en área Tecnología e Informática"]
    assert run(chromium, FakeAira(logged=False), tmp_path).status == "sin_sesion"
    assert run(chromium, FakeAira(applied=True), tmp_path).status == "ya_postulada"
