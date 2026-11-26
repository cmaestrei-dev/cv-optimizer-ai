"""Publicaciones de LinkedIn donde etiquetan a la persona, en un LinkedIn falso con la estructura real (2026-11-26):
menciones con `highlightedUpdateUrn`/`dashCommentUrn`, texto en `expandable-text-box`, enlaces externos en
/safety/go/?url=…, afiche de `media.licdn.com/…/feedshare…` y comentarios después del cuadro de comentarios. Los
enlaces de los avisos miden 0 px de alto, como en la página real. Sin red."""

import dataclasses
import re
import struct
import zlib
from types import SimpleNamespace

import pytest

from runner import __main__ as cli
from runner import config as cfg
from runner import linkedin_posts as lp
from runner.api import ApiError, Vacancy
from runner.state import State

playwright = pytest.importorskip("playwright.sync_api")


def png(width: int = 400, height: int = 300) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


COMMENT_MENTION = ("https://www.linkedin.com/feed/?highlightedUpdateUrn=urn%3Ali%3Aactivity%3A7528184931739566080"
                   "&highlightedUpdateType=MENTIONED_YOU_IN_THIS&origin=inapp&showCommentBox=true"
                   "&commentUrn=urn%3Ali%3Acomment%3A7528184901892898816&dashCommentUrn=urn%3Ali%3Afsd_comment%3A"
                   "%287528184901892898816%2Curn%3Ali%3Aactivity%3A7528058303977893888%29")
POST_MENTION = ("https://www.linkedin.com/feed/?highlightedUpdateUrn=urn%3Ali%3Aactivity%3A7530000000000000000"
                "&highlightedUpdateType=MENTIONED_YOU_IN_THIS")

HIDDEN = "display: flex; height: 0; overflow: hidden"  # el enlace real del aviso mide 0 px de alto (2026-11-26)
NOTIFICATIONS = f"""<html><body><main><h2>Menciones</h2>
<div><div><a style="{HIDDEN}" href="{COMMENT_MENTION}"><span></span><span></span></a>
  <span>Daniela Maestre te ha mencionado en un comentario</span>
  <p>🚀 ¡En Grupo Bruno Fritsch buscamos un/a Ingeniero/a de Automatización e IA!</p></div><span>1 sem</span></div>
<div><a style="{HIDDEN}" href="{POST_MENTION}"><span></span><span></span></a><p>Ana Gómez te ha mencionado en una publicación</p></div>
<div><a href="{COMMENT_MENTION.replace('origin=inapp', 'origin=otro')}">Daniela Maestre te ha mencionado en un comentario</a></div>
</main></body></html>"""

POSTER = "https://media.licdn.com/dms/image/v2/D4E22AQ/feedshare-shrink_800/B4E/0/1794?e=1&v=beta&t=x"
FULL = ("🚀 ¡En Grupo Bruno Fritsch buscamos un/a Ingeniero/a de Automatización e IA! Requisitos: Python y n8n. "
        "Envía tu HV a talento@brunofritsch.cl.")
POST = f"""<html><body><main><section aria-label="Contenido principal">
<a href="https://www.linkedin.com/in/camilomaestre-dev/">Camilo Maestre</a>
<img src="https://media.licdn.com/dms/image/v2/X/profile-displaybackgroundimage-shrink_200_800/0/1">
<img src="https://media.licdn.com/dms/image/v2/Y/company-logo_400_400/0/1">
<a href="https://www.linkedin.com/premium/products/">Premium</a>
<h2>Publicación en el feed</h2>
<a href="https://www.linkedin.com/in/antonia-macias/"></a>
<a href="https://www.linkedin.com/in/antonia-macias/"><div>Antonia Macias</div><div> • 3er+</div></a>
<div><span data-testid="expandable-text-box">🚀 ¡En Grupo Bruno Fritsch buscamos un/a Ingeniero/a de Automatización e IA!…</span>
  <button onclick="document.querySelector('[data-testid=expandable-text-box]').innerText = FULL">…más</button></div>
<a href="https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fbrunofritsch%2Etrabajando%2Ecl%2Ftrabajo%2F6144725-ingeniero&">
  Ingeniero/a de Automatización e IA Grupo Bruno Fritsch - Portal de Empleos</a>
<a href="https://www.linkedin.com/jobs/view/ingeniero-de-ia-en-bruno-4312345678/?trk=x">Ver empleo</a>
<a href="https://www.linkedin.com/feed/hashtag/?keywords=empleo">#empleo</a>
<img src="{POSTER}">
<img src="https://media.licdn.com/dms/image/v2/Z/image-shrink_1280/0/3?t=z">
<div data-testid="ui-core-tiptap-text-editor-wrapper"><div contenteditable="true"></div></div>
<div data-testid="ReactionFacepileCollection-urn:li:activity:7528058303977893888"></div>
<a href="https://www.linkedin.com/in/danielamaestre/">Daniela Maestre</a>
<span data-testid="expandable-text-box">Camilo Maestre</span>
<a href="https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fotro.example%2Fcomentario">un enlace en un comentario</a>
<img src="https://media.licdn.com/dms/image/v2/C/feedshare-shrink_800/0/2?t=y">
</section></main><script>const FULL = {FULL!r};</script></body></html>"""


@pytest.fixture(scope="module")
def chromium():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Sin Chromium para Playwright: {e}")
        yield b
        b.close()


def fake_linkedin(page, *, login=False):
    page.route("**/*", lambda route, request: route.abort())

    def handle(route, request):
        url = request.url
        if login:  # redirección con JavaScript: las HTTP simuladas escapan de page.route
            return route.fulfill(status=200, content_type="text/html", body="<script>location.href = "
                                 "'https://www.linkedin.com/uas/login'</script>") if "/notifications" in url else \
                route.fulfill(status=200, content_type="text/html", body="<main>Inicia sesión</main>")
        if "/notifications/" in url:
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=NOTIFICATIONS)
        if "/feed/update/urn:li:activity:7528058303977893888/" in url:
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=POST)
        return route.fulfill(status=404, body="")

    page.route(re.compile(r"https://www\.linkedin\.com/.*"), handle)
    page.route(re.compile(r"https://media\.licdn\.com/.*"),
               lambda route, request: route.fulfill(status=200, content_type="image/png", body=png()))


def test_reads_mentions_and_the_post_without_its_comments(chromium):
    page = chromium.new_page()
    fake_linkedin(page)
    try:
        found = lp.mentions(page, wait_ms=3000)
        assert [(m.activity, m.who) for m in found] == [
            ("7528058303977893888", "Daniela Maestre te ha mencionado en un comentario"),  # la publicación, no el comentario
            ("7530000000000000000", "Ana Gómez te ha mencionado en una publicación")]       # una vez por publicación
        post = lp.read_post(page, "7528058303977893888", wait_ms=3000)
    finally:
        page.close()
    assert post.author == "Antonia Macias" and post.text == FULL  # «…más» desplegado
    assert post.links == [
        ("https://brunofritsch.trabajando.cl/trabajo/6144725-ingeniero",
         "Ingeniero/a de Automatización e IA Grupo Bruno Fritsch - Portal de Empleos"),
        ("https://www.linkedin.com/jobs/view/4312345678/", "Ver empleo")]  # ni hashtags ni enlaces de los comentarios
    assert post.images == [(png(), "image/png")] * 2  # las de la publicación: ni el logo, ni el fondo, ni los comentarios
    assert post.job_links == ["https://www.linkedin.com/jobs/view/4312345678/"]
    assert post.other_links == ["https://brunofritsch.trabajando.cl/trabajo/6144725-ingeniero"]
    assert post.vacancy_text().startswith("Publicación de LinkedIn de Antonia Macias:\n\n🚀")
    assert "- Ver empleo — https://www.linkedin.com/jobs/view/4312345678/" in post.vacancy_text()


def test_stops_at_a_login_or_verification(chromium):
    page = chromium.new_page()
    fake_linkedin(page, login=True)
    try:
        with pytest.raises(lp.SessionError):
            lp.mentions(page, wait_ms=1000)
    finally:
        page.close()


def test_links_are_read_without_opening_them():
    assert lp.post_activity(COMMENT_MENTION) == "7528058303977893888"
    assert lp.post_activity(POST_MENTION) == "7530000000000000000"
    assert lp.post_activity("https://www.linkedin.com/feed/update/urn:li:activity:123/") == "123"
    assert lp.post_activity("https://www.linkedin.com/in/alguien/") == ""
    assert lp.link_target("https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fempresa.co%2Fempleo&trk=x") == \
        "https://empresa.co/empleo"
    assert lp.link_target("https://www.linkedin.com/jobs/search/?currentJobId=42&geoId=1") == \
        "https://www.linkedin.com/jobs/view/42/"
    assert lp.link_target("https://www.linkedin.com/in/alguien/") == ""
    assert lp.link_target("https://www.linkedin.com/safety/go/?url=javascript%3Aalert(1)") == ""
    assert lp.link_target("https://evil-linkedin.com/safety/go/?url=https%3A%2F%2Fx.co") == "https://evil-linkedin.com/safety/go/?url=https%3A%2F%2Fx.co"
    assert lp.portal_offer("https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-qa-en-cali-A1B2C3D4E5F6A7B8C9")
    assert lp.portal_offer("https://www.elempleo.com/co/ofertas-trabajo/desarrollador-1886660123") == "elempleo"
    assert lp.portal_offer("https://www.magneto365.com/co/empleos/analista-de-datos-12345") == "magneto"
    assert lp.portal_offer("https://fakecomputrabajo.com/ofertas-de-trabajo/x-A1B2C3D4E5F6A7B8C9") == ""
    assert lp.emails_in("Escribe a RRHH@Empresa.com.co. o a talento@x.io") == ["RRHH@Empresa.com.co", "talento@x.io"]
    assert not lp.Post("1", text="Feliz cumpleaños, hermano 🎉").looks_like_job()
    assert lp.Post("1", text="¡Estamos contratando! Envía tu hoja de vida").looks_like_job()
    assert lp.Post("1", text="Mira esto", images=[(b"x", "image/png")]).looks_like_job()


class FakeApi:
    def __init__(self, *, score=80, fail=None, link_status=None):
        self.score, self.fail, self.link_status = score, fail, link_status
        self.posts, self.added, self.statuses = [], [], []

    def post(self, path, body):
        self.posts.append((path, body))
        if path == "/vacancies":
            if self.link_status:
                raise ApiError(self.link_status, "no se pudo", {"application_id": 7} if self.link_status == 409 else {})
            return {"id": 5, "role": "Ingeniero de IA", "company": "Bruno Fritsch"}
        if path.endswith("/status"):
            self.statuses.append(body)
            return {}
        raise AssertionError(path)

    def add_vacancy(self, *, text, url, posted, images=()):
        if self.fail:
            raise ApiError(self.fail, "La entrada no contiene información válida de una vacante.")
        self.added.append((text, url, list(images)))
        return Vacancy(9, True, "Ingeniero/a de Automatización e IA", "Grupo Bruno Fritsch", self.score, [], "guardada")

    def get(self, path):
        assert path == "/applications/9"
        return {"vacancy_text": "…\n\nTexto de la imagen:\nPostúlate escribiendo a seleccion@brunofritsch.cl",
                "language": "es"}

    def make_cv(self, app_id):
        return {"id": 31, "filename": "Camilo_Maestre_IA.pdf"}

    def download_cv(self, cv_id, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF")
        return dest


@pytest.fixture
def conf(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cli, "_foreign", lambda api, conf, app_id: "")
    sent = []
    from runner import telegram

    monkeypatch.setattr(telegram, "add_manual", lambda item: sent.append(item) or True)
    config = cfg.Config(api="http://127.0.0.1:9", token="t", min_scores={"linkedin": 50},
                        include_words=["ingenier", "desarroll"], exclude_words=["senior"])
    return config, sent


POSTED = lp.Post("7528058303977893888", "Antonia Macias", FULL,
                 [("https://brunofritsch.trabajando.cl/trabajo/6144725-ingeniero", "Portal de Empleos")], [(png(), "image/png")])


def test_a_post_with_a_poster_gets_its_cv_and_goes_to_telegram(conf):
    config, sent = conf
    api = FakeApi()
    record = cli._handle_post(api, config, POSTED, "Daniela Maestre te ha mencionado en un comentario")
    assert record == {"estado": "manual", "app": 9}
    (text, url, images), = api.added
    assert url == POSTED.url and images == [(png(), "image/png")] and "trabajando.cl" in text
    item, = sent
    assert (item["titulo"], item["puntaje"], item["url"]) == ("Ingeniero/a de Automatización e IA", 80, POSTED.url)
    assert item["cv"].endswith("Camilo_Maestre_IA.pdf")
    assert item["nota"] == ("Daniela Maestre te ha mencionado en un comentario. Cómo postular: envía tu CV a "
                            "talento@brunofritsch.cl, seleccion@brunofritsch.cl (mira en la publicación si piden un asunto). "
                            "Enlace de la publicación: https://brunofritsch.trabajando.cl/trabajo/6144725-ingeniero")


def test_linked_portal_offers_go_to_the_inbox(conf):
    config, sent = conf
    post = lp.Post("1", "Ana", "Buscamos QA", [("https://www.linkedin.com/jobs/view/4312345678/", "")])
    api = FakeApi()
    assert cli._handle_post(api, config, post, "") == {"estado": "bandeja", "apps": [5]}
    assert api.posts == [("/vacancies", {"url": "https://www.linkedin.com/jobs/view/4312345678/", "prepare": False})]
    assert cli._handle_post(FakeApi(link_status=409), config, post, "") == {"estado": "bandeja", "apps": [7]}
    assert cli._handle_post(FakeApi(link_status=503), config, post, "") is None  # se reintenta en otra vuelta
    assert api.added == [] and sent == []


@pytest.mark.parametrize("post, expected", [
    (lp.Post("1", text="Feliz cumpleaños 🎉"), "no_es_vacante"),
    (lp.Post("1", text="Vacante: inscríbete y debes cancelar el valor del curso de alturas"), "estafa"),
])
def test_posts_that_are_not_vacancies_or_are_scams_never_reach_the_ai(conf, post, expected):
    config, sent = conf
    api = FakeApi()
    assert cli._handle_post(api, config, post, "")["estado"] == expected
    assert api.posts == api.added == sent == []


def test_low_match_excluded_or_not_a_vacancy_are_discarded(conf):
    config, sent = conf
    api = FakeApi(score=30)
    record = cli._handle_post(api, config, POSTED, "")
    assert record == {"estado": "descartada", "app": 9, "motivo": "compatibilidad 30 (mínimo 50)"}
    assert api.posts == [("/applications/9/status", {"status": "descartada",
                                                     "note": "El bot la descartó: compatibilidad 30 (mínimo 50)."})]
    config.exclude_words.append("automatización")
    assert cli._handle_post(FakeApi(), config, POSTED, "")["motivo"] == "el cargo contiene «automatización»"
    assert cli._handle_post(FakeApi(fail=422), config, POSTED, "")["estado"] == "no_es_vacante"
    assert cli._handle_post(FakeApi(fail=429), config, POSTED, "") is None
    assert sent == []


def test_the_round_reads_each_post_once(conf, monkeypatch):
    config, sent = conf
    import playwright.sync_api as sync_api

    from runner import browser

    class Session:
        def __enter__(self):
            return SimpleNamespace()

        def __exit__(self, *exc):
            return False

    closed = []
    page = SimpleNamespace(set_default_timeout=lambda ms: None)
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: Session())
    monkeypatch.setattr(browser, "open_context", lambda p: SimpleNamespace(pages=[page], close=lambda: closed.append(1)))
    monkeypatch.setattr(lp, "mentions", lambda page: [lp.Mention("7528058303977893888", "Daniela Maestre te ha mencionado")])
    monkeypatch.setattr(lp, "read_post", lambda page, activity: POSTED)
    state = State(cfg.DATA_DIR / "estado.json")
    assert cli._linkedin_posts(FakeApi(), config, state) == 1 and len(sent) == 1
    saved = State(cfg.DATA_DIR / "estado.json").data["publicaciones"]["7528058303977893888"]
    assert (saved["estado"], saved["app"], saved["quien"], saved["autor"]) == ("manual", 9, "Daniela Maestre te ha mencionado",
                                                                              "Antonia Macias")
    assert cli._linkedin_posts(FakeApi(), config, State(cfg.DATA_DIR / "estado.json")) == 0 and len(sent) == 1
    assert closed == [1, 1]


SEARCH_PAGE = """<html><body><main><h2>Publicación en el feed</h2><p>En TP estamos contratando Desarrollador Avaya…</p></main>
<script type="application/json">{"key":"reactionState-urn:li:activity:7531784612994260992"}
{"key":"reactionState-urn:li:activity:7531777923356491776","share":"urn:li:share:7531784612260261888"}
{"again":"reactionState-urn:li:activity:7531784612994260992"}</script>
<div style="height:5000px"></div><script>
  let asked = false;
  window.addEventListener('scroll', () => { if (!asked) { asked = true;  // más resultados al bajar (como el real)
    fetch('/flagship-web/rsc-action/actions/component?componentId=search', {method: 'POST'}); } });
</script></body></html>"""


def test_search_reads_the_post_ids_from_the_server_responses(chromium):
    page = chromium.new_page()
    page.route("**/*", lambda route, request: route.abort())
    asked = []

    def handle(route, request):
        if "/search/results/content/" in request.url:
            asked.append(request.url)
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=SEARCH_PAGE)
        if "/flagship-web/rsc-action/" in request.url:
            return route.fulfill(status=200, content_type="text/plain",
                                 body='0:{"k":"reactionState-urn%3Ali%3Aactivity%3A7531529635902148608"}')
        return route.fulfill(status=404, body="")

    page.route(re.compile(r"https://www\.linkedin\.com/.*"), handle)
    try:
        ids = lp.search(page, "estamos contratando desarrollador", period="semana", scrolls=1)
    finally:
        page.close()
    assert ids == ["7531784612994260992", "7531777923356491776", "7531529635902148608"]  # en orden, sin repetir
    assert "keywords=estamos%20contratando%20desarrollador" in asked[0] and "past-week" in asked[0]


def test_posts_found_by_searching_are_filtered_without_ai(conf):
    config, _ = conf
    seeker = lp.Post("1", text="¡Hola a todos! Estoy buscando un nuevo empleo como desarrollador. #OpenToWork")
    assert seeker.job_seeker() and cli._skip_post(seeker, config) == {"estado": "busca_empleo"}
    assert cli._skip_post(lp.Post("2", text="Feliz viernes, equipo"), config) == {"estado": "no_es_vacante"}
    sales = lp.Post("3", text="Estamos contratando vendedores con experiencia comprobable")
    assert cli._skip_post(sales, config)["estado"] == "no_encaja"  # ninguna palabra de [incluir]
    assert cli._skip_post(lp.Post("4", text="Estamos contratando Desarrollador Avaya en Colombia, remoto"), config) is None


@pytest.mark.parametrize("location, modality, reason", [
    ("Guayaquil, Ecuador", "Presencial", "es en Guayaquil, Ecuador y no es remota"),
    ("Lima, Perú", "Remoto", ""),           # remota: sirve desde Colombia
    ("Bogotá", "Híbrido", ""),
    ("Santiago de Cali", "Presencial", ""),  # «Santiago» solo no es Chile
    ("", "", ""),
])
def test_vacancies_abroad_that_are_not_remote_are_discarded(conf, location, modality, reason):
    config = dataclasses.replace(conf[0], home_country="Colombia")
    assert cli._abroad({"vacancy": {"location": location, "modality": modality}}, config) == reason


def test_the_round_also_hunts_posts_by_searching(conf, monkeypatch):
    config, sent = conf
    config = dataclasses.replace(config, mentions=False, post_max=2,
                                 post_searches=["estamos contratando desarrollador", "vacante desarrollador junior"])
    import playwright.sync_api as sync_api

    from runner import browser

    class Session:
        def __enter__(self):
            return SimpleNamespace()

        def __exit__(self, *exc):
            return False

    page = SimpleNamespace(set_default_timeout=lambda ms: None)
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: Session())
    monkeypatch.setattr(browser, "open_context", lambda p: SimpleNamespace(pages=[page], close=lambda: None))
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    searched = []
    monkeypatch.setattr(lp, "mentions", lambda page: pytest.fail("las menciones están apagadas"))
    monkeypatch.setattr(lp, "search", lambda page, words, period: searched.append(words) or ["11", "22", "33"])
    posts = {"11": lp.Post("11", "Ana", "Estoy buscando un nuevo empleo como desarrollador #OpenToWork"), "22": POSTED}
    monkeypatch.setattr(lp, "read_post", lambda page, activity: posts[activity])
    api = FakeApi()
    assert cli._linkedin_posts(api, config, State(cfg.DATA_DIR / "estado.json")) == 2
    assert searched == ["estamos contratando desarrollador"]  # con 2 de máximo, la segunda búsqueda no hace falta
    saved = State(cfg.DATA_DIR / "estado.json").data["publicaciones"]
    assert saved["11"]["estado"] == "busca_empleo" and saved["22"]["estado"] == "manual" and "33" not in saved
    assert len(api.added) == 1 and sent[0]["nota"].startswith("La encontró el bot buscando «estamos contratando desarrollador»")
