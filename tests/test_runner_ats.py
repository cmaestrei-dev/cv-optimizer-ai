"""Vigilar portales de empresas en Workday (Accenture…) y Eightfold (Mercado Libre) con sus APIs públicas, sin red."""

import json
from datetime import date

import pytest

from runner import config as cfg
from runner import eightfold, watch, workday
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
