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
LOGIN = "https://career8.successfactors.com/career?company=X&loginFlowRequired=true&lang=es_ES"


def radio(qid: int, label: str, options: list[str]) -> str:
    opts = "".join(
        f'<span id="{qid + i + 1}:_radio" onclick="pick(\'{qid}\', {qid + i + 1})"><span id="{qid + i + 1}:_anchor" '
        f'role="radio" aria-checked="false" aria-labelledby="{qid + i + 1}:_radiolabel"></span>'
        f'<label id="{qid + i + 1}:_radiolabel" class="radioLabel">{o}</label></span>' for i, o in enumerate(options))
    return (f'<label id="{qid}:l" for="{qid}:" class="rcmFormQuestionLabel"><span class="requiredField">*</span>&nbsp;'
            f'{label}</label><div id="{qid}:" role="radiogroup" aria-labelledby="{qid}:l">{opts}</div>')


class FakeSF:
    def __init__(self, *, logged: bool = True, job_section: bool = True):
        self.logged, self.applied, self.posted, self.job_section = logged, 1, [], job_section
        self.profile_cv, self.saved = "Camilo_Maestre_Backend_Junior.pdf", []  # subir el CV en el formulario lo cambia también aquí
        self.ignore_saves = False

    def _form(self) -> str:
        # Como el real: los valores cuentan cuando el formulario los recibe (change o clic), subir el CV o elegir en
        # una lista redibuja (lo respondido se pierde y los campos del perfil se ven vacíos un momento), y «Detalles»
        # depende de «¿Cómo supo de este puesto?».
        return f"""<html><body><a>Salir</a><span>Ampliar todas las secciones</span>
          <div>Puestos vacantes: Ingeniero/a de Software Backend (Junior) (66157)</div>
          <div>Mis documentos * Currículum Descargar documento <span id="cv-name">CV_viejo.pdf</span> Última modificación: 01/04/2026
            <span id="41:_attachIcon" onclick="document.getElementById('42:_file').style.display='block'">✎</span>
            <input type="file" id="42:_file" style="display:none" onchange="uploaded(this)"></div>
          <div><label for="87:_input" class="rcmFormFieldLabel"><span class="requiredField">*</span>&nbsp;País de nacimiento</label>
            <input id="87:_input" role="combobox" value="Colombia" onkeydown="menu(this, ['Colombia', 'Venezuela'])"></div>
          <div>{"<h3>Información específica del puesto</h3>" if self.job_section else ""}
            <label for="800:_input" class="rcmFormFieldLabel"><span class="requiredField">*</span>&nbsp;¿Cómo supo de este puesto?</label>
            <input id="800:_input" role="combobox" onkeydown="menu(this, ['Otros Portales de Empleo', 'Portal de Empleo Externo'])">
            <label for="810:_input" class="rcmFormFieldLabel"><span class="requiredField">*</span>&nbsp;Detalles</label>
            <input id="810:_input" role="combobox"
                   onkeydown="menu(this, model['800:_input'] === 'Portal de Empleo Externo' ? ['empleo.grupobancolombia.com'] : ['Indeed'])">
            {radio(700, "¿Tienes algún pariente, cónyuge o persona con relación análoga que trabaje actualmente con Bancolombia?",
                   ["1 familiar", "Mas de 3 familiares", "No tengo familiares en Bancolombia"])}
            {radio(710, "¿Cómo te enteraste de esta vacante?",
                   ["LinkedIn: La encontré navegando en LinkedIn.", "Portal de empleo de Bancolombia: Apliqué directamente."])}
            {radio(720, "¿Tienes experiencia con Kubernetes?", ["Si.", "No."])}
            <label for="730:" class="rcmFormQuestionLabel"><span class="requiredField">*</span>&nbsp;¿Cuál es tu salario actual o último salario?</label>
            <textarea id="730:" onchange="model[this.id] = this.value"></textarea>
            <label for="740:" class="rcmFormQuestionLabel"><span class="requiredField">*</span>&nbsp;¿Cuál es tu nivel de formación académica?</label>
            <select id="740:" onchange="model[this.id] = this.value"><option>1-Bachiller</option><option>5-6 a 10 semestre carrera universitaria</option></select>
            <label for="750:" class="rcmFormQuestionLabel">¿Algo más que quieras contarnos?</label><textarea id="750:"></textarea>
          </div>
          <label for="837:_txtFld" class="rcmFormFieldLabel"><span class="requiredField">*</span>&nbsp;Si estás de acuerdo con la Declaración de Conformidad, por favor escribe tu nombre completo a continuación.</label>
          <input type="text" id="837:_txtFld" name="disclaimerAcknowledge" onchange="model.firma = this.value">
          <ul id="menu"></ul>
          <span id="apply" onclick="send()">Aplicar</span>
          <script>
            const model = {{}};
            function pick(group, id) {{
              document.querySelectorAll('[id="' + group + ':"] [role=radio]').forEach(r => r.setAttribute('aria-checked', 'false'));
              document.getElementById(id + ':_anchor').setAttribute('aria-checked', 'true');
              model[group] = document.getElementById(id + ':_radiolabel').innerText; }}
            function menu(input, items) {{
              const ul = document.getElementById('menu'); ul.innerHTML = '';
              for (const it of items) {{ const li = document.createElement('li'); li.className = 'globalMenuItem'; li.innerText = it;
                li.onclick = () => {{ input.value = it; model[input.id] = it; ul.innerHTML = ''; redraw(); }}; ul.appendChild(li); }} }}
            function redraw() {{  // un campo del perfil se ve vacío mientras se redibuja (aquí: sus dos primeras lecturas)
              let reads = 0;
              Object.defineProperty(document.getElementById('87:_input'), 'value',
                                    {{configurable: true, get: () => ++reads > 2 ? 'Colombia' : '', set: () => {{}}}}); }}
            function uploaded(f) {{
              document.getElementById('cv-name').innerText = f.files[0].name;
              for (const k of Object.keys(model)) delete model[k];  // se redibuja: lo respondido se pierde
              document.querySelectorAll('[role=radio]').forEach(r => r.setAttribute('aria-checked', 'false'));
              document.querySelectorAll('textarea, input[type=text], input[role=combobox]').forEach(e => e.value = '');
              redraw(); }}
            async function send() {{
              await fetch('/apply', {{method: 'POST', body: JSON.stringify({{model, cv: document.getElementById('cv-name').innerText}})}});
              document.body.insertAdjacentHTML('beforeend', '<p>Gracias por postularte</p>'); }}
          </script></body></html>"""

    def handle(self, route, request):
        url = urlparse(request.url)
        if url.path == "/apply":
            self.posted.append(json.loads(request.post_data))
            self.applied += 1
            return route.fulfill(status=200, content_type="application/json", body="{}")
        if url.path == "/save":
            if not self.ignore_saves:
                self.profile_cv = request.post_data
                self.saved.append(self.profile_cv)
            return route.fulfill(status=200, content_type="application/json", body="{}")
        if url.path == "/career":  # el acceso: con sesión lleva al perfil con el código de la sesión (`_s.crb`)
            body = ('<html><body><script>location.href = "/portalcareer?company=X&navBarLevel=MY_PROFILE&_s.crb=tok"</script></body></html>'
                    if self.logged else '<html><body><input type="password"></body></html>')
        elif "navBarLevel=MY_PROFILE" in request.url and "_s.crb=tok" not in request.url:  # el enlace directo, como en el real
            body = "<html><body>The requested operation is not available. You are not authorized to access the functionality you have requested.</body></html>"
        elif "navBarLevel=MY_PROFILE" in request.url:  # «Mis documentos» carga cerrada, como en el real
            body = f"""<html><body><a>Salir</a> Puestos solicitados ({self.applied})
              <span onclick="document.getElementById('docs').style.display='block'">Ampliar todas las secciones</span>
              <div id="docs" style="display:none">Mis documentos * Currículum Descargar documento <span id="cv-name">{self.profile_cv}</span>
                Última modificación: 22/11/2026
                <span id="41:_attachIcon" onclick="document.getElementById('42:_file').style.display='block'">✎</span>
                <input type="file" id="42:_file" style="display:none" onchange="document.getElementById('cv-name').innerText = this.files[0].name">
                <span class="rcmSaveButton" onclick="save()">Guardar</span></div><p id="msg"></p>
              <script>async function save() {{
                await fetch('/save', {{method: 'POST', body: document.getElementById('cv-name').innerText}});
                document.getElementById('msg').innerText = 'Perfil del candidato guardado correctamente.'; }}</script></body></html>"""
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


def open_page(chromium, fake):
    page = chromium.new_page()
    page.route("**/*", lambda route, request: route.abort())  # nada sale a la red
    page.route(re.compile(r"https://(empleo\.grupobancolombia\.com|career8\.successfactors\.com)/.*"), fake.handle)
    return page


def run(chromium, fake, tmp_path, *, submit=True, answers=None):
    page = open_page(chromium, fake)
    cv = tmp_path / "Camilo_Maestre_Backend_Junior.pdf"
    cv.write_bytes(b"%PDF-1.4")
    known = {"¿Tienes experiencia con Kubernetes?": "Si."} if answers is None else answers
    overrides = {"pariente, conyuge|relacion analoga": "No tengo familiares en Bancolombia",
                 "como supo de este puesto": "Portal de Empleo Externo", "detalles": "empleo.grupobancolombia.com",
                 "como te enteraste": "Portal de empleo de Bancolombia", "nivel de formacion academica": "5-6 a 10 semestre carrera universitaria",
                 "salario actual|ultimo salario": "2000000"}
    try:
        return sf.apply(page, OFFER, cv, lambda qs: {q.label: known[q.label] for q in qs if q.label in known}, submit=submit,
                        full_name="Camilo Andres Maestre Iglesias", overrides=overrides, login_url=LOGIN)
    finally:
        page.close()


def test_applies_with_this_vacancys_cv_and_the_bank(chromium, tmp_path):
    fake = FakeSF()
    result = run(chromium, fake, tmp_path)
    assert result.status == "enviada" and "pasó de 1 a 2" in result.detail, result  # contado en el perfil, entrando por el acceso
    (sent,) = fake.posted
    assert sent["model"] == {
        "800:_input": "Portal de Empleo Externo", "810:_input": "empleo.grupobancolombia.com",  # lista en cascada
        "700": "No tengo familiares en Bancolombia", "710": "Portal de empleo de Bancolombia: Apliqué directamente.",
        "720": "Si.", "730:": "2000000", "740:": "5-6 a 10 semestre carrera universitaria",
        "firma": "Camilo Andres Maestre Iglesias"}  # todo confirmado después de subir el CV; el país del perfil, intacto
    assert sent["cv"] == "Camilo_Maestre_Backend_Junior.pdf"


def test_a_form_without_the_job_section_still_opens(chromium, tmp_path):
    # Front Mobile (2026-11-26): el formulario no traía «Información específica del puesto» y el lote lo daba por no abierto
    fake = FakeSF(job_section=False)
    assert run(chromium, fake, tmp_path).status == "enviada" and len(fake.posted) == 1


def test_dry_run_unanswered_and_no_session_never_send(chromium, tmp_path):
    fake = FakeSF()
    assert run(chromium, fake, tmp_path, submit=False).status == "revisada" and fake.posted == []
    skipped = run(chromium, fake, tmp_path, answers={})  # nadie sabe lo de Kubernetes: no se envía
    assert skipped.status == "saltada" and skipped.unanswered == ["¿Tienes experiencia con Kubernetes?"] and fake.posted == []
    assert run(chromium, FakeSF(logged=False), tmp_path).status == "sin_sesion"


def test_the_general_cv_goes_back_to_the_profile(chromium, tmp_path):
    fake = FakeSF()
    general = tmp_path / "Camilo_Maestre_Desarrollador_de_Software_Full_Stack.pdf"
    general.write_bytes(b"%PDF-1.4")
    page = open_page(chromium, fake)
    try:
        assert sf.restore_cv(page, LOGIN, general) == ""  # abre «Mis documentos», cambia el CV, guarda y lo confirma
        assert fake.profile_cv == general.name and fake.saved == [general.name]
        assert sf.restore_cv(page, LOGIN, general) == "" and fake.saved == [general.name]  # ya estaba: no guarda otra vez
        fake.ignore_saves = True  # el portal no guarda: se dice en qué paso falló y queda la captura
        other = tmp_path / "Otro_CV.pdf"
        other.write_bytes(b"%PDF-1.4")
        shot = tmp_path / "capturas" / "perfil.png"
        problem = sf.restore_cv(page, LOGIN, other, shot=shot)
        assert problem.startswith(f"tras guardar, el perfil sigue con «{general.name}»") and shot.exists()
    finally:
        page.close()
