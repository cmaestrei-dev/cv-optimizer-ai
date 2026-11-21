"""Postular en elempleo contra un elempleo falso (Playwright intercepta sus direcciones): sin red ni cuenta real.

El falso imita lo observado el 2026-11-21: «Postularme a oferta» hace un POST a `/co/JobOffers/JobOfferDetail/Save`
que responde JSON con `Response`, y la oferta queda con `"offerapplied": true`. Necesita Playwright y un Chromium;
si no están (p. ej. en la CI), se salta.
"""

import html
import json
import re
from urllib.parse import parse_qs, urlparse

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from runner import elempleo_apply  # noqa: E402

OFFER = "https://www.elempleo.com/co/ofertas-trabajo/practicante-ingenieria-en-sistemas-1886801108"




class FakeElempleo:
    def __init__(self, *, logged: bool = True, applied: bool = False, code: int = 1, quick: bool = False,
                 video: str = "", attachments: tuple = ("1897633635",)):
        self.logged, self.applied, self.code, self.quick, self.video = logged, applied, code, quick, video
        self.attachments, self.posts, self.outside = attachments, [], []

    def _offer(self) -> str:
        flags = {"applypostlogin": False, "offerapplied": self.applied}
        return f"""<html><body><h1>Practicante Ingeniería en Sistemas</h1>
          {'<a href="https://www.elempleo.com/co/Account/LogOff">Cerrar sesión</a>' if self.logged else '<a>Ingresar</a>'}
          <input class="js-hdnvars" id="hdnvars" type="hidden" value="{html.escape(json.dumps(flags))}">
          <form><input name="__RequestVerificationToken" type="hidden" value="tok-1"></form>
          <form><input name="__RequestVerificationToken" type="hidden" value="tok-2"></form>
          <input type="hidden" class="js-config" data-is-quick-offer-application="{self.quick}" data-is-vip="False">
          <input type="hidden" id="vprezInputHidden" data-vprez-url="{self.video}" data-apply-post-login="False">
          <form action="/co/JobOffers/JobOfferDetail/SaveQuickApplication?JobOfferId=1886801108&amp;CurrentAttachmentCVId=0"
                class="js-quick-application-form" enctype="multipart/form-data" method="post">
            <input name="__RequestVerificationToken" type="hidden" value="tok-q">
            <select class="form-control js-select-file" name="Attachments.SelectedIds">
              <option disabled="disabled" selected="selected" value="-1">Selecciona una opción</option>
              {"".join(f'<option value="{a}">CV_{a}.pdf</option>' for a in self.attachments)}
            </select>
            <input class="attachment-file js-attachment-file" name="File" type="file"></form>
          <button class="btn js-apply-offer" type="button" data-url="/co/JobOffers/JobOfferDetail/Save?jobOfferId=1886801108">
            Postularme a oferta</button>
          <script>
            document.querySelector('.js-apply-offer').onclick = async function () {{
              const r = await fetch(this.dataset.url, {{method: 'POST', body: '__RequestVerificationToken=x',
                headers: {{'Content-Type': 'application/x-www-form-urlencoded'}}}});
              const t = await r.json();
              if (t.Response === 2) window.open('https://empresa.example/aplicar', '_blank');
              else if (t.Response === 4 || t.Response === 5) location.href = t.Url;
            }};
          </script></body></html>"""

    def handle(self, route, request):
        url = urlparse(request.url)
        if url.path.startswith("/co/JobOffers/JobOfferDetail/SaveQuickApplication") and request.method == "POST":
            self.posts.append(("rapida", request.post_data))
            self.applied = self.code in (1, 2)
            return route.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"Response": self.code, "Url": "/co/x", "ModelInvalid": False}))
        if url.path.startswith("/co/JobOffers/JobOfferDetail/Save") and request.method == "POST":
            self.posts.append((request.post_data, request.headers.get("x-requested-with")))
            self.applied = self.code in (1, 2)
            where = "https://empresa.example/aplicar" if self.code == 2 else "/co/ofertas-trabajo/x-1886801108"
            body = {"Response": self.code, "Url": where, "ModelInvalid": False}
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        if url.path.startswith("/co/ofertas-trabajo/"):
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self._offer())
        return route.fulfill(status=200, content_type="text/html", body="<html></html>")


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
def no_waits(monkeypatch):
    monkeypatch.setattr(elempleo_apply.time, "sleep", lambda s: None)


def run(chromium, fake: FakeElempleo, *, submit: bool = True):
    page = chromium.new_page()
    page.route("**/*", lambda route, request: (fake.outside.append(request.url), route.abort()))  # nada sale a la red
    page.route(re.compile(r"https://www\.elempleo\.com/.*"), fake.handle)
    try:
        return elempleo_apply.apply(page, OFFER, None, lambda qs: {}, submit=submit)
    finally:
        page.close()


def test_applies_with_the_offer_button_and_confirms_it(chromium):
    fake = FakeElempleo()
    result = run(chromium, fake)
    assert result.status == "enviada" and result.detail == "Confirmada en la oferta" and not result.follow_up
    assert fake.posts == [("__RequestVerificationToken=tok-1", "XMLHttpRequest")]  # como la página: el primer token
    assert fake.outside == []


def test_dry_run_and_stops_never_send(chromium):
    dry = FakeElempleo()
    assert run(chromium, dry, submit=False).status == "revisada" and dry.posts == []
    for fake, status in ((FakeElempleo(applied=True), "ya_postulada"), (FakeElempleo(logged=False), "sin_sesion"),
                         (FakeElempleo(quick=True, attachments=()), "externa")):
        result = run(chromium, fake)
        assert result.status == status and fake.posts == [], status
    assert run(chromium, FakeElempleo(quick=True, attachments=())).follow_up  # sin PDF que elegir: a la persona


def test_quick_application_sends_the_cv_attached_to_the_profile(chromium):
    fake = FakeElempleo(quick=True, attachments=("1897633635", "222"))
    assert run(chromium, fake, submit=False).status == "revisada" and fake.posts == []
    result = run(chromium, fake)
    assert result.status == "enviada" and result.detail == "Confirmada en la oferta"
    (kind, body), = fake.posts
    sent = parse_qs(body)
    assert kind == "rapida" and sent["Attachments.SelectedIds"] == ["1897633635"]  # el primer PDF (el CV general)
    assert sent["IsQuickApplicationOffer"] == ["True"] and sent["__RequestVerificationToken"] == ["tok-q"]
    assert "File" not in sent  # nunca sube archivos: quedarían también en la hoja de vida


def test_company_site_and_video_steps_go_to_the_person(chromium):
    fake = FakeElempleo(code=2)
    result = run(chromium, fake)
    assert result.status == "enviada" and "https://empresa.example/aplicar" in result.follow_up
    assert fake.outside == []  # el bot no abre el sitio de la empresa
    video = run(chromium, FakeElempleo(video="https://vprez.example/v/1"))
    assert video.status == "enviada" and "videocuestionario" in video.follow_up


def test_incomplete_profile_and_already_applied_answers(chromium):
    assert run(chromium, FakeElempleo(code=3)).status == "perfil"
    assert run(chromium, FakeElempleo(code=4)).status == "ya_postulada"
