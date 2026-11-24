"""Postular en un Eightfold falso con la estructura de los reales (Mercado Libre y Softtek, 2026-11-24): CV, contacto,
listas de país, preguntas de texto, radios «Si»/«No», listas y la autorización obligatoria. Sin red ni cuenta."""

import json
import re

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from runner import eightfold_apply as ef  # noqa: E402

OFFER = "https://jobs.softtek.com/careers/job/893398420149"


def combo(cid: str, label_id: str, options: list[str], *, aria_label: str = "") -> str:
    items = "".join(f'<li role="option">{o}</li>' for o in options)
    extra = f' aria-label="{aria_label}"' if aria_label else ""
    return (f'<input role="combobox" id="{cid}" aria-controls="list-{cid}" aria-labelledby="{label_id}" aria-required="true"'
            f' placeholder="Seleccionar"{extra} oninput="filter(this)" onclick="openList(this)">'
            f'<ul id="list-{cid}" hidden data-all=\'{json.dumps(options)}\'>{items}</ul>')


COUNTRIES = ["Afganistán", "Chile", "Colombia", "Costa Rica"]
CODES = ["Chile (+56)", "Colombia (+57)", "Costa Rica (+506)"]
FORM = f"""<html><body><form onsubmit="return false">
<input type="file" id="cv" accept=".docx,.doc,.pdf" onchange="parsed(this)"><div id="cvname"></div>
<label id="Informaci_n_de_contacto_email_label" for="Informaci_n_de_contacto_email">Correo electrónico*</label>
<input id="Informaci_n_de_contacto_email" aria-required="true">
<label id="Informaci_n_de_contacto_firstname_label" for="Informaci_n_de_contacto_firstname">Nombre*</label>
<input id="Informaci_n_de_contacto_firstname" aria-required="true">
<label id="Informaci_n_de_contacto_lastname_label" for="Informaci_n_de_contacto_lastname">Apellido*</label>
<input id="Informaci_n_de_contacto_lastname" aria-required="true">
{combo("input-9", "", CODES, aria_label="Código de país")}
<input id="Informaci_n_de_contacto_phone" aria-required="true">
<span id="pais_label">País</span>{combo("input-12", "pais_label", COUNTRIES)}
<label id="Informaci_n_de_contacto_city_label" for="Informaci_n_de_contacto_city">Ciudad*</label>
<input id="Informaci_n_de_contacto_city" aria-required="true">
<label id="Preguntas_sobre_la_solicitud_LinkedIn_label" for="Preguntas_sobre_la_solicitud_LinkedIn">LinkedIn</label>
<input id="Preguntas_sobre_la_solicitud_LinkedIn">
<label id="q1_label" for="q1"><span>¿Cuántos años de experiencia tiene en un puesto similar?</span></label>
<input id="q1" aria-required="true">
<label id="q2_label" for="q2"><span><div>¿Actualmente estás laborando?</div></span></label>
<div role="radiogroup" id="q2"><input type="radio" name="q2" id="q2-Si" value="Si" aria-required="true"><label for="q2-Si"></label>
  <input type="radio" name="q2" id="q2-No" value="No" aria-required="true"><label for="q2-No"></label></div>
<label id="q3_label" for="q3">Nivel de Inglés</label>{combo("input-16", "q3_label", ["Básico", "Intermedio", "Avanzado"])}
<label id="q4_label" for="q4">¿Aceptas la Declaración de Privacidad de Mercado Libre?</label>{combo("input-18", "q4_label", ["Sí", "No"])}
<p>¿Autorizas que te contactemos por WhatsApp para comunicarte avances sobre tu postulación?</p>
<input type="checkbox" id="wa" name="q_whatsapp_authorize" aria-required="true"><label for="wa">Estoy de acuerdo</label>
<input type="checkbox" id="save" checked><label for="save">Guardar mis respuestas para futuras solicitudes</label>
<button type="button">Cancelar</button><button type="submit" onclick="send()">Enviar solicitud</button>
</form><script>
function parsed(input) {{  // como Softtek: primero el acuerdo de privacidad; luego lee el CV y llena el contacto
  document.body.insertAdjacentHTML('beforeend', '<div role="dialog" id="agree"><p>Acuerdo de privacidad de datos</p>' +
    '<button type="button" onclick="document.getElementById(\\'agree\\').remove(); loaded()">Estoy de acuerdo</button></div>'); }}
function loaded() {{
  document.getElementById('cvname').innerText = document.getElementById('cv').files[0].name;
  document.getElementById('Informaci_n_de_contacto_firstname').value = 'CAMILO';
  document.getElementById('Informaci_n_de_contacto_email').value = 'otro@correo.com'; }}
function openList(input) {{ document.getElementById(input.getAttribute('aria-controls')).hidden = false; }}
function filter(input) {{ const ul = document.getElementById(input.getAttribute('aria-controls')); ul.hidden = false;
  ul.innerHTML = JSON.parse(ul.dataset.all).filter(o => o.toLowerCase().includes(input.value.toLowerCase()))
    .map(o => '<li role="option">' + o + '</li>').join(''); }}
document.addEventListener('click', e => {{ if (e.target.getAttribute('role') === 'option') {{ const ul = e.target.parentElement;
  const input = document.querySelector('[aria-controls="' + ul.id + '"]'); input.value = e.target.innerText; ul.hidden = true; }} }});
async function send() {{
  const v = id => document.getElementById(id).value;
  const data = {{email: v('Informaci_n_de_contacto_email'), first: v('Informaci_n_de_contacto_firstname'),
    last: v('Informaci_n_de_contacto_lastname'), phone: v('Informaci_n_de_contacto_phone'), code: v('input-9'), country: v('input-12'),
    city: v('Informaci_n_de_contacto_city'), linkedin: v('Preguntas_sobre_la_solicitud_LinkedIn'), years: v('q1'),
    working: (document.querySelector('[name=q2]:checked') || {{}}).value, english: v('input-16'), privacy: v('input-18'),
    whatsapp: document.getElementById('wa').checked, save: document.getElementById('save').checked}};
  await fetch('/api/apply', {{method: 'POST', body: JSON.stringify(data)}});
  document.body.innerHTML = CHALLENGE ? '<iframe src="https://www.google.com/recaptcha/api2/bframe?k=x" style="width:300px;height:300px"></iframe>'
                                      : '<h2>¡Gracias por tu postulación!</h2>'; }}
</script></body></html>"""


class FakeEightfold:
    def __init__(self, *, challenge=False, already=False):
        self.challenge, self.already, self.posts = challenge, already, []

    def handle(self, route, request):
        if request.method == "POST":
            self.posts.append(json.loads(request.post_data))
            return route.fulfill(status=200, content_type="application/json", body="{}")
        if self.already:
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body="<p>Ya te has postulado a este empleo</p>")
        body = FORM.replace("CHALLENGE ?", "true ?" if self.challenge else "false ?")
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
    monkeypatch.setattr(ef.time, "sleep", lambda s: None)


CONTACT = {"full_name": "Camilo Andres Maestre Iglesias", "email": "camilo@example.com", "phone": "+57 305 000 0000",
           "city": "Cartagena", "linkedin_url": "https://www.linkedin.com/in/camilo"}


def run(chromium, fake, tmp_path, *, submit=True, known=None):
    page = chromium.new_page()
    page.route("**/*", lambda route, request: route.abort())
    page.route(re.compile(r"https://jobs\.softtek\.com/.*"), fake.handle)
    cv = tmp_path / "Camilo_Maestre_FullStack_Softtek.pdf"
    cv.write_bytes(b"%PDF-1.4")
    known = {"¿Cuántos años de experiencia tiene en un puesto similar?": "1", "¿Actualmente estás laborando?": "Sí",
             "Nivel de Inglés": "Básico"} if known is None else known
    try:
        return ef.apply(page, OFFER, cv, lambda qs: {q.label: known[q.label] for q in qs if q.label in known}, submit=submit,
                        contact=CONTACT, overrides={"declaracion de privacidad": "Sí"})
    finally:
        page.close()


def test_fills_everything_and_sends(chromium, tmp_path):
    fake = FakeEightfold()
    result = run(chromium, fake, tmp_path)
    assert result.status == "enviada" and "Gracias" in result.detail, result
    assert fake.posts == [{"email": "camilo@example.com", "first": "Camilo Andres", "last": "Maestre Iglesias", "phone": "3050000000",
                           "code": "Colombia (+57)", "country": "Colombia", "city": "Cartagena",
                           "linkedin": "https://www.linkedin.com/in/camilo", "years": "1", "working": "Si", "english": "Básico",
                           "privacy": "Sí", "whatsapp": True, "save": False}]  # nunca «guardar mis respuestas»


def test_dry_run_unanswered_challenge_and_already_applied(chromium, tmp_path):
    fake = FakeEightfold()
    assert run(chromium, fake, tmp_path, submit=False).status == "revisada" and fake.posts == []
    skipped = run(chromium, FakeEightfold(), tmp_path, known={"Nivel de Inglés": "Básico"})
    assert skipped.status == "saltada" and "¿Cuántos años de experiencia tiene en un puesto similar?" in skipped.unanswered
    assert run(chromium, FakeEightfold(challenge=True), tmp_path).status == "verificacion"  # nunca se resuelve
    assert run(chromium, FakeEightfold(already=True), tmp_path).status == "ya_postulada"


def test_apply_link():
    assert ef.apply_url(OFFER) == "https://jobs.softtek.com/careers/apply?pid=893398420149"
    assert ef.apply_url("https://mercadolibre.eightfold.ai/careers/job/45431215") == \
        "https://mercadolibre.eightfold.ai/careers/apply?pid=45431215"
    with pytest.raises(ValueError):
        ef.apply_url("https://jobs.softtek.com/careers")
