"""Vigilar portales de empresas en Workday (Accenture…) y Eightfold (Mercado Libre) con sus APIs públicas, sin red."""

import json
from datetime import date, datetime, timedelta

import pytest

from runner import config as cfg
from runner import eightfold, getonbrd, watch, workday
from runner.discover import BlockedError

MELI = watch.Site(name="Mercado Libre", base="https://mercadolibre.eightfold.ai", terms=[], portal="eightfold",
                  country="Colombia", domain="mercadolibre.com")
ACCENTURE = watch.Site(name="Accenture", base="https://accenture.wd103.myworkdayjobs.com/es/AccentureCareers", terms=[],
                       portal="workday", country="Colombia")


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch):
    monkeypatch.setattr(watch, "pause", lambda low, high: None)


def _position(pid: int, name: str, place: str) -> dict:  # como las de `data.positions` (Mercado Libre, 2026-11-22)
    return {"id": pid, "displayJobId": str(pid)[-6:], "name": name, "locations": [place], "postedTs": 1795209159,
            "workLocationOption": "hybrid", "positionUrl": f"/careers/job/{pid}"}


def test_eightfold_lists_the_country_pages_and_skips_remote_jobs_elsewhere():
    pages = {0: [_position(44629730 + i, f"Analista {i}", "Bogotá,Colombia") for i in range(9)]
             + [_position(1, "Remote Engineer", "Remote, Brazil")],
             10: [_position(45626386, "Ingeniero de Seguridad Cloud", "Medellín,Colombia")]}
    calls = []

    def get(url):
        calls.append(url)
        start = int(url.split("start=")[1].split("&")[0])
        return {"status": 200, "data": {"positions": pages.get(start, []), "count": 11}}

    rows = eightfold.listing(MELI, get=get)
    assert len(rows) == 10 and ("1", "Remote Engineer", "https://mercadolibre.eightfold.ai/careers/job/1") not in rows
    assert rows[-1] == ("45626386", "Ingeniero de Seguridad Cloud", "https://mercadolibre.eightfold.ai/careers/job/45626386")
    assert len(calls) == 2 and "domain=mercadolibre.com" in calls[0] and "location=Colombia" in calls[0]
    assert "sort_by=timestamp" in calls[0] and "query=" not in calls[0]


def test_eightfold_posting_reads_the_description():
    detail = {"data": {"name": "Analista de Desarrollo de Software Backend", "locations": ["Bogotá,Colombia"],
                       "postedTs": 1795008598, "publicUrl": "https://mercadolibre.eightfold.ai/careers/job/45592600",
                       "jobDescription": "<div><h2>Descripción breve - externa</h2><p>Diseñar APIs.</p><ul><li>Go</li><li>SQL</li></ul></div>"}}
    seen = []
    info = eightfold.posting(MELI, "https://mercadolibre.eightfold.ai/careers/job/45592600",
                             get=lambda url: seen.append(url) or detail)
    assert "position_id=45592600" in seen[0] and "hl=es" in seen[0]
    assert info["title"] == "Analista de Desarrollo de Software Backend" and info["place"] == "Bogotá,Colombia"
    assert info["text"] == "Descripción breve - externa\nDiseñar APIs.\n- Go\n- SQL"
    assert info["posted"] == date.fromtimestamp(1795008598) and info["closes"] is None


FACETS = [  # como en Workday: los países pueden venir dentro de un grupo de facetas
    {"facetParameter": "jobFamilyGroup", "descriptor": "Área", "values": [{"descriptor": "Tecnología", "id": "t1", "count": 9}]},
    {"facetParameter": "locationMainGroup", "descriptor": "Ubicaciones", "values": [
        {"facetParameter": "locationCountry", "descriptor": "País", "values": [
            {"descriptor": "Argentina", "id": "ar1", "count": 50},
            {"descriptor": "Colombia", "id": "e8106cd6a3534f2dba6fdee2d41db89d", "count": 21}]}]},
]


def _job(n: int) -> dict:
    return {"title": f"IT Customer Service {n}", "externalPath": f"/job/Medellin/IT-Customer-Service_R0000{n:03d}",
            "locationsText": "Medellín", "postedOn": "Posted Today", "bulletFields": [f"R0000{n:03d}"]}


def test_workday_finds_the_country_by_name_and_pages_through_it():
    calls = []

    def post(url, body):
        calls.append((url, body))
        if body["limit"] == 1:
            return {"total": 900, "facets": FACETS, "jobPostings": [_job(999)]}
        jobs = [_job(i) for i in range(body["offset"], min(body["offset"] + 20, 21))]
        return {"total": 21, "jobPostings": jobs}

    rows = workday.listing(ACCENTURE, post=post)
    assert calls[0][0] == "https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs"
    assert calls[1][1]["appliedFacets"] == {"locationCountry": ["e8106cd6a3534f2dba6fdee2d41db89d"]}
    assert len(rows) == 21 and len(calls) == 3  # facetas + 2 páginas
    assert rows[0] == ("R0000000", "IT Customer Service 0",
                       "https://accenture.wd103.myworkdayjobs.com/AccentureCareers/job/Medellin/IT-Customer-Service_R0000000")


def test_workday_without_the_country_says_so():
    with pytest.raises(ValueError, match="Colombia"):
        workday.listing(ACCENTURE, post=lambda url, body: {"total": 1, "facets": FACETS[:1], "jobPostings": []})


def test_workday_posting_reads_the_offer_from_its_public_link():
    seen = []
    detail = {"jobPostingInfo": {"title": "IT Customer Service", "location": "Medellín",
                                 "jobDescription": "<p>Soporte a usuarios.</p><ul><li>Windows</li></ul>",
                                 "startDate": "2026-11-20", "endDate": "2026-12-20"}}
    info = workday.posting(ACCENTURE, "https://accenture.wd103.myworkdayjobs.com/AccentureCareers/job/Medellin/IT_R0000001",
                           get=lambda url: seen.append(url) or detail)
    assert seen == ["https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/job/Medellin/IT_R0000001"]
    assert info["text"] == "Soporte a usuarios.\n- Windows" and info["place"] == "Medellín"
    assert info["posted"] == date(2026, 11, 20) and info["closes"] == date(2026, 12, 20)


def test_check_runs_every_portal_and_a_blocked_one_waits(monkeypatch):
    def fake(url, body=None):
        if "myworkdayjobs" in url:
            raise BlockedError("el portal frenó las peticiones (HTTP 429)")
        return {"data": {"positions": [_position(7, "Desarrollador Backend Junior", "Bogotá,Colombia"),
                                       _position(8, "Analista de Transporte", "Bogotá,Colombia")], "count": 2}}

    monkeypatch.setattr(watch, "request_json", fake)
    data = {}
    new = watch.check([ACCENTURE, MELI], data, get=lambda url: pytest.fail("SuccessFactors no se usa aquí"))
    assert [n["cargo"] for n in new] == ["Desarrollador Backend Junior"]  # «Analista de Transporte» no encaja
    assert set(data["vigiladas"]) == {"Mercado Libre:7", "Mercado Libre:8"}


def test_new_portals_in_the_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[[vigilar]]\nnombre = "Mercado Libre"\nportal = "eightfold"\nsitio = "https://mercadolibre.eightfold.ai"\n'
                    'dominio = "mercadolibre.com"\npais = "Colombia"\n\n'
                    '[[vigilar]]\nnombre = "Accenture"\nportal = "workday"\n'
                    'sitio = "https://accenture.wd103.myworkdayjobs.com/AccentureCareers"\npais = "Colombia"\n', encoding="utf-8")
    meli, accenture = watch.load_sites(path)
    assert (meli.portal, meli.domain, meli.country, meli.terms) == ("eightfold", "mercadolibre.com", "Colombia", [])
    assert accenture.portal == "workday" and accenture.base.endswith("/AccentureCareers")
    for bad in ('portal = "workday"\nsitio = "https://x.wd1.myworkdayjobs.com/Careers"\n',  # sin país
                'portal = "eightfold"\nsitio = "https://x.eightfold.ai"\npais = "Colombia"\n',  # sin dominio
                'portal = "workday"\nsitio = "https://x.wd1.myworkdayjobs.com/C"\npais = "Colombia"\npostular = true\n',
                'portal = "greenhouse"\nsitio = "https://x"\npais = "Colombia"\n'):
        path.write_text('[[vigilar]]\nnombre = "X"\n' + bad, encoding="utf-8")
        with pytest.raises(cfg.ConfigError):
            watch.load_sites(path)


def test_request_json_turns_a_block_into_blocked_error(monkeypatch):
    import io
    import urllib.error

    def refuse(request, timeout):
        assert json.loads(request.data) == {"limit": 1} and request.get_header("Content-type") == "application/json"
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, io.BytesIO(b""))

    monkeypatch.setattr(watch.urllib.request, "urlopen", refuse)
    with pytest.raises(BlockedError):
        watch.request_json("https://x.wd1.myworkdayjobs.com/wday/cxs/x/C/jobs", {"limit": 1})


def test_a_portal_that_blocks_waits_without_using_the_round(tmp_path, monkeypatch):
    # Caso real (2026-11-22): 7 de las 10 ofertas de la vuelta fueron de Accenture y frenaron; Mercado Libre no entró.
    from runner import __main__ as cli
    from runner import telegram
    from runner.state import State
    from tests.test_runner_watch import FakeApi

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    state = State(tmp_path / "estado.json")
    state.data["vigiladas"] = {
        **{f"Accenture:R{i}": {"cargo": f"Application Developer {i}", "url": f"https://a/job/R{i}", "encaja": True} for i in range(3)},
        "Mercado Libre:7": {"cargo": "Desarrollador Backend Junior", "url": "https://mercadolibre.eightfold.ai/careers/job/7", "encaja": True},
    }
    read = []

    def posting(site, url):
        read.append(site.name)
        if site.portal == "workday":
            raise BlockedError("el portal frenó las peticiones (HTTP 429)")
        return {"title": "Desarrollador Backend Junior", "place": "Bogotá,Colombia", "text": "Python y APIs", "posted": None, "closes": None}

    monkeypatch.setattr(watch, "read_posting", posting)
    monkeypatch.setattr(telegram, "add_manual", lambda item: True)
    api = FakeApi(score=70)
    assert cli._prepare_watched(api, state, [ACCENTURE, MELI], limit=1) == 1
    assert read == ["Accenture", "Mercado Libre"]  # tras el primer freno no insiste con Accenture
    assert state.data["vigiladas"]["Mercado Libre:7"]["app"] == 1
    assert all("app" not in state.data["vigiladas"][f"Accenture:R{i}"] for i in range(3))  # esperan a la próxima vuelta


# --- Get on Board -----------------------------------------------------------------------------------------------

GOB = watch.Site(name="Get on Board", base="https://www.getonbrd.com", terms=[], portal="getonbrd", country="Colombia",
                 include=watch.BOARD_INCLUDE, exclude=watch.BOARD_EXCLUDE)
TODAY = date(2026, 11, 22)


def _gob(slug: str, title: str, *, level=2, category="Programming", lang="es", countries=("Colombia",), days=3) -> dict:
    published = int((datetime(2026, 11, 22, 12) - timedelta(days=days)).timestamp())
    return {"id": slug, "type": "job", "links": {"public_url": f"https://www.getonbrd.com/jobs/{slug}"},
            "attributes": {"title": title, "category_name": category, "lang": lang, "countries": list(countries),
                           "remote_modality": "hybrid", "published_at": published,
                           "seniority": {"data": {"id": level, "type": "seniority"}}}}


def test_getonbrd_keeps_recent_tech_jobs_for_juniors_in_the_country():
    jobs = [_gob("agente-mesa-ti", "Agente de Mesa de Servicios TI", category="Technical Support"),
            _gob("sre-engineer", "SRE Engineer", level=3, category="SysAdmin / DevOps / QA"),
            _gob("backend-senior", "Back-end Developer", level=4),  # senior
            _gob("ejecutivo", "Ejecutivo Comercial", category="Sales"),  # no es de tecnología
            _gob("remote-en", "Data Engineer", lang="en", countries=("Remote",)),  # en inglés y no es de una sede aquí
            _gob("viejo", "Desarrollador Junior", days=40)]  # publicada hace más de un mes
    calls = []
    rows = getonbrd.listing(GOB, get=lambda url: calls.append(url) or {"data": jobs, "meta": {"total_pages": 1}}, today=TODAY)
    assert [r[0] for r in rows] == ["agente-mesa-ti", "sre-engineer"]
    assert "country_code=CO" in calls[0] and "per_page=100" in calls[0] and len(calls) == 1
    assert all(watch.matches(GOB, title) for _, title, _ in rows)  # la categoría ya dice que es de tecnología
    assert not watch.matches(GOB, "AI Sales Development Representative") and not watch.matches(GOB, "DBA Oracle Bilingüe")
    with pytest.raises(ValueError, match="Narnia"):
        getonbrd.listing(watch.Site(name="X", base=GOB.base, terms=[], portal="getonbrd", country="Narnia"), get=lambda url: {})


GOB_PAGE = """<div class="bg-gradient-main" id="right-col" itemscope itemtype="http://schema.org/JobPosting">
<time datetime="2026-10-15T02:01:02+00:00" itemprop="datePosted"></time>
<span itemprop="jobLocation" itemscope><span itemprop="address" itemscope><meta content="Medellín" itemprop="addressLocality">
<meta content="CO" itemprop="addressCountry"></span></span>
<h1><span itemprop="title">
Agente de Mesa de Servicios TI </span><span class="fake-hidden size-3"> en Factor IT </span></h1>
<div class="my2" itemprop="hiringOrganization" itemscope><a href="/companies/factor-it"><img alt="Factor IT" src="x.png"></a></div>
<div id="job-body" itemprop="description"><div class="gb-rich-txt"><p>Soporte a usuarios.</p><ul><li>Windows</li><li>Redes</li></ul></div></div>
<footer>Fuera de la oferta</footer></div>"""


def test_getonbrd_posting_comes_from_the_public_page(monkeypatch):
    monkeypatch.setattr(watch, "fetch", lambda url: GOB_PAGE)
    info = getonbrd.posting(GOB, "https://www.getonbrd.com/jobs/agente-mesa-ti")
    assert info == {"title": "Agente de Mesa de Servicios TI", "place": "Medellín, CO", "text": "Soporte a usuarios.\n- Windows\n- Redes",
                    "posted": date(2026, 10, 15), "closes": None, "company": "Factor IT"}


def test_a_job_board_offer_goes_to_the_app_with_its_own_company(tmp_path, monkeypatch):
    from runner import __main__ as cli
    from runner import telegram
    from runner.state import State
    from tests.test_runner_watch import FakeApi

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(watch, "fetch", lambda url: GOB_PAGE)
    state = State(tmp_path / "estado.json")
    state.data["vigiladas"] = {"Get on Board:agente-mesa-ti": {"cargo": "Agente de Mesa de Servicios TI", "encaja": True,
                                                               "url": "https://www.getonbrd.com/jobs/agente-mesa-ti"}}
    sent = []
    monkeypatch.setattr(telegram, "add_manual", lambda item: sent.append(item) or True)
    api = FakeApi(score=72)
    assert cli._prepare_watched(api, state, [GOB]) == 1
    assert api.added[0][0].startswith("Agente de Mesa de Servicios TI\nFactor IT\nMedellín, CO")  # la empresa, no la bolsa
    assert sent[0]["empresa"] == "Factor IT" and "Get on Board" in sent[0]["nota"]
