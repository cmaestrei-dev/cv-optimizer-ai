"""Postular en un AIRA falso como el de Falabella (2026-11-23): el formulario Vue con el CV que sube su componente,
la expectativa salarial, los años en deslizadores y las dos casillas que vienen marcadas. Sin red ni cuenta."""

import json
import re

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from runner import aira_apply as aira  # noqa: E402

OFFER = "https://falabella.airavirtual.com/postula/EDUCkJCruw7wrgHJjoWa?logged_action=apply&register=true"

FORM = """<html><body><h1>Estado postulación</h1><p>Practicante Area de Sistemas</p> <p>Falabella Equipo Corporativo</p>
<div id="form">
 <div id="filewrap"><input type="file" id="cv" style="display:none"><span>resume.pdf</span></div>
 <label>Expectativa salarial (bruto mensual pesos COP)</label><input type="text" placeholder="Ej: 1.000.000" id="salary" value="3.000.000">
 <p>Años de experiencia en área Tecnología e Informática</p>
 <div id="s1">RADIOS</div>
 <p>Nivel de conocimiento en Excel</p>
 <div id="s2">LEVELS</div>
 <label><input type="checkbox" id="save" checked> Guardar hoja de vida en mi perfil</label>
 <label><input type="checkbox" id="alerts" checked> Recibir alertas de empleo de esta empresa</label>
 <a id="send" onclick="send()">ENVIAR POSTULACIÓN</a></div>
<script>
 const formVm = {$options: {methods: {uploadCv() {}}}, $set(o, k, v) { o[k] = v; },
   general_info_group: {SALARY: {answer: '3000000'}, RESUME_SOURCE: {answer: 'PROFILE'}},
   specific_questions_groups: {work_experience: [{id: 1, type: 'slider', text: 'Años de experiencia en área Tecnología e Informática',
                                                   answer: null, data: {param_validation: 'required|max:200', levels: 'experience_years'}}],
                               knowledge: [{id: 2, type: 'slider', text: 'Nivel de conocimiento en Excel', answer: null,
                                            data: {param_validation: 'required|max:50', levels: 'experience_levels'}}]}};
 document.getElementById('form').__vue__ = formVm;
 document.getElementById('filewrap').__vue__ = {$options: {name: 'FileWithPreview'}, $parent: formVm, async changedFile() {
   const f = document.getElementById('cv').files[0];
   await fetch('/applicant-api/v1/applications/1/test/1/step/1/save_answers', {method: 'POST', body: JSON.stringify({cv: f.name})});
   formVm.general_info_group.RESUME_SOURCE.answer = 'UPLOADED'; }};
 document.getElementById('s1').__vue__ = {$options: {name: 'Slider'},
   handleChangeRadiosSlider(e) { formVm.specific_questions_groups.work_experience[0].answer = e[0].value; }};
 document.getElementById('s2').__vue__ = {$options: {name: 'Slider'},
   handleChangeRadiosSlider(e) { formVm.specific_questions_groups.knowledge[0].answer = e[0].value; }};
 async function send() {
   const missing = !document.getElementById('salary').value || formVm.specific_questions_groups.work_experience[0].answer === null ||
     formVm.specific_questions_groups.knowledge[0].answer === null;
   if (missing) { document.body.insertAdjacentHTML('beforeend', '<p>Campo requerido</p>'); return; }
   await fetch('/applicant-api/v1/applications/1/test/1/step/2/save_answers', {method: 'POST', body: JSON.stringify({
     salary: document.getElementById('salary').value, years: formVm.specific_questions_groups.work_experience[0].answer,
     excel: formVm.specific_questions_groups.knowledge[0].answer,
     save_cv: document.getElementById('save').checked, alerts: document.getElementById('alerts').checked})});
   document.body.innerHTML = '<h1>Estado postulación</h1><p>Practicante Area de Sistemas</p><p>Pruebas Personalidad (D32) 15 minutos Pendiente COMPLETAR</p>'; }
</script></body></html>""".replace("RADIOS", "".join(f'<input type="radio" name="q_1" value="{v}"><label>{v if v < 5 else "5+ años"}</label>'
                                                     for v in range(6))).replace("LEVELS", "".join(
    f'<input type="radio" name="q_2" value="{v}"><label>{label}</label>' for v, label in (
        ("none", "Ninguno"), ("basic", "Básico"), ("middle", "Intermedio"), ("advanced", "Avanzado"), ("expert", "Experto"))))


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
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body="<html><body>Estado postulación Practicante Area de Sistemas Falabella Equipo Corporativo Pruebas</body></html>")
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


def run(chromium, fake, tmp_path, *, submit=True, known=None, title="Practicante Área de Sistemas"):
    page = chromium.new_page()
    page.route("**/*", lambda route, request: route.abort())
    page.route(re.compile(r"https://falabella\.airavirtual\.com/.*"), fake.handle)
    cv = tmp_path / "Camilo_Maestre_Practicante_Area_de_Sistemas.pdf"
    cv.write_bytes(b"%PDF-1.4")
    known = {"Años de experiencia en área Tecnología e Informática": "1", "Nivel de conocimiento en Excel": "Avanzado",
             "Expectativa salarial (bruto mensual pesos COP)": "3000000"} if known is None else known
    try:
        return aira.apply(page, OFFER, cv, lambda qs: {q.label: known[q.label] for q in qs if q.label in known}, submit=submit,
                          title=title)
    finally:
        page.close()


def test_uploads_this_vacancys_cv_answers_and_sends(chromium, tmp_path):
    fake = FakeAira()
    result = run(chromium, fake, tmp_path)
    assert result.status == "enviada" and "pruebas" in result.follow_up, result
    upload, sent = fake.posts
    assert upload == {"cv": "Camilo_Maestre_Practicante_Area_de_Sistemas.pdf"}
    assert sent == {"salary": "3000000", "years": "1", "excel": "advanced", "save_cv": False, "alerts": False}  # sin guardar el CV ni alertas


def test_an_internship_without_a_figure_asks_for_the_usual_stipend(chromium, tmp_path):
    fake = FakeAira()
    assert run(chromium, fake, tmp_path, known={"Años de experiencia en área Tecnología e Informática": "7",  # 5+ años
                                                "Nivel de conocimiento en Excel": "Intermedio"}).status == "enviada"
    assert fake.posts[-1]["salary"] == str(aira.INTERNSHIP_SALARY) and fake.posts[-1]["years"] == "5"
    assert fake.posts[-1]["excel"] == "middle"


def test_dry_run_unanswered_no_session_and_already_applied(chromium, tmp_path):
    fake = FakeAira()
    assert run(chromium, fake, tmp_path, submit=False).status == "revisada" and len(fake.posts) == 1  # solo el CV
    skipped = run(chromium, FakeAira(), tmp_path, known={})
    assert skipped.status == "saltada" and skipped.unanswered == ["Años de experiencia en área Tecnología e Informática",
                                                                  "Nivel de conocimiento en Excel"]
    assert run(chromium, FakeAira(logged=False), tmp_path).status == "sin_sesion"
    assert run(chromium, FakeAira(applied=True), tmp_path).status == "ya_postulada"


def test_never_fills_the_form_of_another_vacancy(chromium, tmp_path):
    # Caso real: AIRA recuerda en la sesión la última postulación elegida y a veces abre esa, de otra vacante.
    fake = FakeAira()
    result = run(chromium, fake, tmp_path, title="DATA ANALYST")
    assert result.status == "error" and "otra postulación" in result.detail and fake.posts == []
