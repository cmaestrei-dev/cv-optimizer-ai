"""Postular en Computrabajo contra un Computrabajo falso (Playwright intercepta sus direcciones): sin red ni cuenta real.

El falso imita lo observado el 2026-11-18: documentos con «por defecto» (máximo 10), «Aplicar» que postula al
abrir /match/?oi=…, preguntas de filtro en /candidate/apply-kq y la oferta marcada «Postulado» después.
Necesita Playwright y un Chromium; si no están (p. ej. en la CI), se salta.
"""

import re
from urllib.parse import parse_qs, urlparse

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from runner import computrabajo_apply as ct  # noqa: E402

OFFER = "https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-auxiliar-contable-AB12CD34EF56AB78"
OI = "AB12CD34EF56AB78"


class FakeComputrabajo:
    def __init__(self, docs: list[str], *, questions: bool = False, logged: bool = True):
        self.docs = [{"id": f"D{i}", "name": n} for i, n in enumerate(docs)]
        self.default, self.next_id, self.applied, self.logged = "0", len(docs), False, logged
        self.questions, self.answers, self.attached, self.outside = questions, {}, None, []

    def _docs_page(self, error: str = "") -> str:
        rows = "".join(
            f'<ul><li><input type="radio" name="rbPrincipal" value="{d["id"]}" {"checked" if d["id"] == self.default else ""}></li>'
            f'<li><a href="#" data-filecandidateid="{d["id"]}">{d["name"]}</a></li>'
            f'<li><span id="it-delete" data-filecandidateid="{d["id"]}" data-filepath="p{d["id"]}">x</span></li></ul>'
            for d in self.docs)
        return f"""<html><body><div id="MainContainer"><span id="it-error">{error}</span>
          <form id="f1" method="post" enctype="multipart/form-data" action="/candidate/cv/uploadcv">
            <input type="file" name="fu" input-file onchange="document.getElementById('f1').submit()"></form>
          <ul><li><input type="radio" name="rbPrincipal" value="0" {"checked" if self.default == "0" else ""}></li></ul>{rows}
          <div id="frmDelete" style="display:none"><button id="btDelete">Eliminar</button></div></div>
          <script>
            document.querySelectorAll('input[name=rbPrincipal]').forEach(r => r.onclick = (e) => {{
              e.preventDefault();  // como el real: no cambia aquí, recarga y la página nueva trae el nuevo por defecto
              location.href = '/candidate/cv/uploadcv?dcf=' + r.value; }});
            document.querySelectorAll('#it-delete').forEach(x => x.onclick = () => {{
              const b = document.getElementById('btDelete'); b.dataset.id = x.dataset.filecandidateid;
              document.getElementById('frmDelete').style.display = 'block'; }});
            document.getElementById('btDelete').onclick = (e) => location.href = '/candidate/cv/uploadcv?dlf=' + e.target.dataset.id;
          </script></body></html>"""

    def _offer_page(self) -> str:
        return f"""<html><body><h1>Auxiliar contable</h1>
          <a data-href-offer-apply="https://candidato.co.computrabajo.com/match/?oi={OI}&p=57" class="b_primary">Aplicar</a>
          <a already-applied-btn style="display:{'inline' if self.applied else 'none'}">Postulado</a>
          <script>window._IsUserLogged = () => {str(self.logged).lower()};
            document.querySelector('[data-href-offer-apply]').onclick = function() {{ location.href = this.dataset.hrefOfferApply; }};
          </script></body></html>"""

    def _kq_page(self) -> str:
        # Igual al real (2026-11-20): el texto de cada pregunta va en un campo oculto, no en una etiqueta asociada.
        return """<html><body><form action="https://www.google.com/search"><input name="q" aria-label="Cargo o categoría"></form>
          <div id="MainContainer"><form action="/candidate/kq" method="post">
            <input type="hidden" name="KillerQuestions[0].Title" value="¿Cuál es tu aspiración salarial?">
            <div class="field_textarea"><label class="fs16">¿Cuál es tu aspiración salarial?</label>
              <textarea name="KillerQuestions[0].OpenQuestion" maxlength="500"></textarea></div>
            <input type="hidden" name="KillerQuestions[1].Title" value="¿Puedes hacer práctica empresarial?">
            <label class="radio"><input type="radio" name="KillerQuestions[1].ClosedQuestion" value="0">
              <span class="input"></span><span class="label_box">SI</span></label>
            <label class="radio"><input type="radio" name="KillerQuestions[1].ClosedQuestion" value="1">
              <span class="input"></span><span class="label_box">NO</span></label>
            <button type="submit">Enviar mi HdV</button></form></div></body></html>"""

    @staticmethod
    def _redirect(route, to: str):
        # Redirección con JavaScript: las redirecciones HTTP de una respuesta simulada no pasan por la intercepción
        # y saldrían a la red real.
        return route.fulfill(status=200, content_type="text/html", body=f"<script>location.replace('{to}')</script>")

    def handle(self, route, request):
        url = urlparse(request.url)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        html = None
        if url.path.startswith("/ofertas-de-trabajo/"):
            html = self._offer_page()
        elif url.path.startswith("/candidate/cv/uploadcv"):
            if not self.logged:
                return self._redirect(route, "/acceso/")
            if request.method == "POST":
                name = re.search(rb'filename="([^"]+)"', request.post_data_buffer).group(1).decode()
                if len(self.docs) >= 10:
                    html = self._docs_page("Se ha alcanzado el número máximo de documentos permitido")
                else:
                    self.docs.append({"id": f"D{self.next_id}", "name": name})
                    self.next_id += 1
            elif "dcf" in query:
                self.default = query["dcf"]
            elif "dlf" in query:
                self.docs = [d for d in self.docs if d["id"] != query["dlf"]]
                self.default = "0" if self.default == query["dlf"] else self.default
            html = html or self._docs_page()
        elif url.path.startswith("/match/"):
            if self.questions and not self.answers:
                return self._redirect(route, f"/candidate/kq?oi={OI}")
            self.applied = True
            self.attached = next((d["name"] for d in self.docs if d["id"] == self.default), None)
            html = "<html><body><h2>¡Te has postulado a la oferta!</h2></body></html>"
        elif url.path.startswith("/candidate/kq"):
            if request.method == "POST":
                self.answers = parse_qs(request.post_data or "")
                return self._redirect(route, f"/match/?oi={OI}")
            html = self._kq_page()
        elif url.path.startswith("/acceso"):
            html = "<html><body>Ingresa</body></html>"
        return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html or "<html></html>")


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Sin Chromium para Playwright: {e}")
        yield b
        b.close()


def _page(browser, fake: FakeComputrabajo):
    page = browser.new_page()
    outside = []
    page.route("**/*", lambda route, request: (outside.append(request.url), route.abort()))  # nada sale a la red
    page.route(re.compile(r"https://(co|candidato\.co)\.computrabajo\.com/.*"), fake.handle)
    fake.outside = outside
    return page


@pytest.fixture
def pdfs(tmp_path):
    general, cv = tmp_path / "Camilo_Maestre_Desarrollador_de_Software.pdf", tmp_path / "Camilo_Maestre_Auxiliar_contable.pdf"
    for f in (general, cv):
        f.write_bytes(b"%PDF-1.4 prueba")
    return general, cv


def answerer(questions):
    known = {"¿Cuál es tu aspiración salarial?": "3000000", "¿Puedes hacer práctica empresarial?": "Sí"}
    return {q.label: known[q.label] for q in questions if q.label in known}


def test_applies_with_this_vacancys_cv_and_leaves_the_general_by_default(browser, pdfs):
    general, cv = pdfs
    fake = FakeComputrabajo([general.name])
    page = _page(browser, fake)
    uploaded: list[str] = []
    result = ct.apply(page, OFFER, cv, answerer, submit=True, general=general, uploaded=uploaded)
    assert result.status == "enviada", result
    assert fake.attached == cv.name  # la empresa recibió el CV de ESTA vacante
    assert next(d["name"] for d in fake.docs if d["id"] == fake.default) == general.name
    assert uploaded == [cv.name]


def test_dry_run_prepares_the_cv_but_never_applies(browser, pdfs):
    general, cv = pdfs
    fake = FakeComputrabajo([general.name])
    result = ct.apply(_page(browser, fake), OFFER, cv, answerer, submit=False, general=general, uploaded=[])
    assert result.status == "revisada" and fake.applied is False
    assert next(d["name"] for d in fake.docs if d["id"] == fake.default) == general.name


def test_makes_room_by_deleting_only_what_the_bot_uploaded(browser, pdfs):
    general, cv = pdfs
    bot_old = [f"bot_{i}.pdf" for i in range(9)]
    fake = FakeComputrabajo([general.name, *bot_old])
    uploaded = list(bot_old)
    result = ct.apply(_page(browser, fake), OFFER, cv, answerer, submit=True, general=general, uploaded=uploaded)
    assert result.status == "enviada", result
    names = [d["name"] for d in fake.docs]
    assert "bot_0.pdf" not in names and general.name in names and cv.name in names and len(names) == 10
    assert uploaded == [*bot_old[1:], cv.name]


def test_never_deletes_documents_it_did_not_upload(browser, pdfs):
    general, cv = pdfs
    fake = FakeComputrabajo([general.name, *[f"tuyo_{i}.pdf" for i in range(9)]])
    result = ct.apply(_page(browser, fake), OFFER, cv, answerer, submit=True, general=general, uploaded=[])
    assert result.status == "sin_espacio" and "ninguno lo subió el bot" in result.detail
    assert fake.applied is False and len(fake.docs) == 10


def test_answers_the_filter_questions_with_the_bank(browser, pdfs):
    general, cv = pdfs
    fake = FakeComputrabajo([general.name], questions=True)
    result = ct.apply(_page(browser, fake), OFFER, cv, answerer, submit=True, general=general, uploaded=[])
    assert result.status == "enviada", result
    assert fake.answers["KillerQuestions[0].OpenQuestion"] == ["3000000"]
    assert fake.answers["KillerQuestions[1].ClosedQuestion"] == ["0"] and fake.attached == cv.name  # «SI»
    assert fake.outside == []  # ni el buscador del encabezado ni nada fuera del Computrabajo falso


def test_unanswered_filter_questions_skip_the_vacancy(browser, pdfs):
    general, cv = pdfs
    fake = FakeComputrabajo([general.name], questions=True)
    result = ct.apply(_page(browser, fake), OFFER, cv, lambda qs: {}, submit=True, general=general, uploaded=[])
    assert result.status == "saltada" and "¿Cuál es tu aspiración salarial?" in result.unanswered
    assert fake.applied is False


def test_already_applied_and_no_session(browser, pdfs):
    general, cv = pdfs
    fake = FakeComputrabajo([general.name])
    fake.applied = True
    assert ct.apply(_page(browser, fake), OFFER, cv, answerer, submit=True, general=general, uploaded=[]).status == "ya_postulada"
    out = FakeComputrabajo([general.name], logged=False)
    assert ct.apply(_page(browser, out), OFFER, cv, answerer, submit=True, general=general, uploaded=[]).status == "sin_sesion"
