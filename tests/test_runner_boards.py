"""Portales de empresas en Recruitee, Greenhouse, Lever, Ashby y SmartRecruiters (APIs públicas), sin red.
Las respuestas imitan las reales del 2026-11-22 (Bold, Clara, Yuno, Addi, Experian), recortadas."""

import pytest

from runner import boards, watch
from runner import config as cfg


def site(portal: str, account: str = "", base: str = "") -> watch.Site:
    return watch.Site(name="Empresa", base=base, terms=[], portal=portal, country="Colombia", account=account)


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch):
    monkeypatch.setattr(watch, "pause", lambda low, high: None)


def router(responses: dict):
    calls = []

    def get(url):
        calls.append(url)
        for prefix, body in responses.items():
            if url.startswith(prefix):
                return body
        raise AssertionError(f"petición inesperada: {url}")
    get.calls = calls
    return get


RECRUITEE = {"offers": [
    {"id": 1, "title": "IT Support Analyst- Colombia", "careers_url": "https://jobs.bold.co/o/it-support", "country_code": "CO",
     "location": "Trabajo a distancia", "locations": [], "description": "<p>Soporte</p>", "requirements": "<ul><li>Redes</li></ul>",
     "published_at": "2026-11-17 10:00:00 UTC", "close_at": "2026-12-01 00:00:00 UTC", "company_name": "Bold"},
    {"id": 2, "title": "Head of Sales - Perú", "careers_url": "https://jobs.bold.co/o/head-sales", "country_code": "PE",
     "location": "Lima, Lima, Perú", "locations": [{"country_code": "PE"}]},
]}


def test_recruitee():
    s, get = site("recruitee", base="https://jobs.bold.co"), router({"https://jobs.bold.co/api/offers/": RECRUITEE})
    assert boards.listing(s, get=get) == [("1", "IT Support Analyst- Colombia", "https://jobs.bold.co/o/it-support")]
    info = boards.posting(s, "https://jobs.bold.co/o/it-support", get=get)
    assert info["text"] == "Soporte\n- Redes" and info["company"] == "Bold"
    assert str(info["posted"]) == "2026-11-17" and str(info["closes"]) == "2026-12-01"


def test_greenhouse():
    s = site("greenhouse", account="clara")
    board = {"jobs": [{"id": 5295539007, "title": "Software Engineer in Test (SDET)", "absolute_url": "https://job-boards.greenhouse.io/clara/jobs/5295539007",
                       "location": {"name": "Bogota / CUN / Colombia; Mexico City / CDMX / Mexico"}},
                      {"id": 9, "title": "Accountant", "absolute_url": "https://job-boards.greenhouse.io/clara/jobs/9",
                       "location": {"name": "Mexico City / CDMX / Mexico"}}]}
    job = {"title": "Software Engineer in Test (SDET)", "location": {"name": "Bogota / CUN / Colombia"}, "company_name": "Clara ",
           "content": "&lt;p&gt;Pruebas &amp;amp; calidad&lt;/p&gt;", "first_published": "2026-11-14T08:02:41-05:00", "application_deadline": None}
    get = router({"https://boards-api.greenhouse.io/v1/boards/clara/jobs/5295539007": job,
                  "https://boards-api.greenhouse.io/v1/boards/clara/jobs": board})
    assert [r[0] for r in boards.listing(s, get=get)] == ["5295539007"]
    info = boards.posting(s, "https://job-boards.greenhouse.io/clara/jobs/5295539007", get=get)
    assert info["text"] == "Pruebas & calidad" and info["company"] == "Clara" and str(info["posted"]) == "2026-11-14"
    assert boards.posting(s, "https://clara.com/careers?gh_jid=5295539007", get=get)["title"].startswith("Software")


def test_lever():
    s = site("lever", account="yuno")
    pid = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
    postings = [{"id": pid, "text": "Technical Support", "country": "CO", "hostedUrl": f"https://jobs.lever.co/yuno/{pid}",
                 "categories": {"location": "Colombia", "allLocations": ["Colombia"]}},
                {"id": "x", "text": "Corporate IT Manager", "country": "IN", "hostedUrl": "https://jobs.lever.co/yuno/x",
                 "categories": {"location": "Hyderabad", "allLocations": ["Hyderabad"]}}]
    detail = {"text": "Technical Support", "categories": {"location": "Colombia"}, "createdAt": 1792506757868,
              "description": "<div>Soporte a comercios</div>", "lists": [{"text": "Requisitos", "content": "<li>SQL</li>"}],
              "additional": ""}
    get = router({f"https://api.lever.co/v0/postings/yuno/{pid}": detail, "https://api.lever.co/v0/postings/yuno": postings})
    assert boards.listing(s, get=get) == [(pid, "Technical Support", f"https://jobs.lever.co/yuno/{pid}")]
    info = boards.posting(s, f"https://jobs.lever.co/yuno/{pid}", get=get)
    assert info["text"] == "Soporte a comercios\nRequisitos\n- SQL" and info["posted"] is not None


def test_ashby():
    s = site("ashby", account="addi")
    jobs = {"jobs": [{"id": "a1", "title": "Backend Engineer | IC2", "jobUrl": "https://jobs.ashbyhq.com/addi/a1", "isListed": True,
                      "location": "LatAm", "address": {"postalAddress": {"addressCountry": "Colombia"}}, "secondaryLocations": [],
                      "descriptionHtml": "<p>APIs en Kotlin</p>", "publishedAt": "2026-05-14T18:21:50.166+00:00"},
                     {"id": "a2", "title": "Backend Engineer", "jobUrl": "https://jobs.ashbyhq.com/addi/a2", "isListed": True,
                      "location": "São Paulo", "address": {"postalAddress": {"addressCountry": "Brazil"}}}]}
    get = router({"https://api.ashbyhq.com/posting-api/job-board/addi": jobs})
    assert [r[0] for r in boards.listing(s, get=get)] == ["a1"]
    assert boards.posting(s, "https://jobs.ashbyhq.com/addi/a1", get=get)["text"] == "APIs en Kotlin"


def test_smartrecruiters_pages_and_reads_the_sections():
    s = site("smartrecruiters", account="Experian")
    page = {"totalFound": 1, "content": [{"id": "744000159666329", "name": "ANALISTA JUNIOR PROCESOS BATCH"}]}
    detail = {"name": "ANALISTA JUNIOR PROCESOS BATCH", "location": {"fullLocation": "Bogotá, , Colombia"}, "company": {"name": "Experian"},
              "releasedDate": "2026-11-04T15:34:25.990Z",
              "jobAd": {"sections": {"jobDescription": {"title": "Funciones", "text": "<p>Monitorear procesos</p>"},
                                     "qualifications": {"title": "Requisitos", "text": "<ul><li>SQL</li></ul>"}}}}
    get = router({"https://api.smartrecruiters.com/v1/companies/Experian/postings/744000159666329": detail,
                  "https://api.smartrecruiters.com/v1/companies/Experian/postings?": page})
    rows = boards.listing(s, get=get)
    assert rows == [("744000159666329", "ANALISTA JUNIOR PROCESOS BATCH", "https://jobs.smartrecruiters.com/Experian/744000159666329")]
    assert "country=co" in get.calls[0]
    info = boards.posting(s, rows[0][2], get=get)
    assert info["text"] == "Funciones\nMonitorear procesos\nRequisitos\n- SQL" and info["company"] == "Experian"


def test_config_needs_the_account_and_builds_the_public_page(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[[vigilar]]\nnombre = "Addi"\nportal = "ashby"\ncuenta = "addi"\npais = "Colombia"\n\n'
                    '[[vigilar]]\nnombre = "Bold"\nportal = "recruitee"\nsitio = "https://jobs.bold.co"\npais = "Colombia"\n',
                    encoding="utf-8")
    addi, bold = watch.load_sites(path)
    assert (addi.account, addi.base) == ("addi", "https://jobs.ashbyhq.com/addi") and bold.base == "https://jobs.bold.co"
    path.write_text('[[vigilar]]\nnombre = "X"\nportal = "greenhouse"\npais = "Colombia"\n', encoding="utf-8")
    with pytest.raises(cfg.ConfigError, match="cuenta"):
        watch.load_sites(path)


def test_sales_titles_never_match():
    s = site("recruitee", base="https://jobs.bold.co")
    assert not watch.matches(s, "Sales Development Representative SDR INBOUND - IT") and watch.matches(s, "IT Support Analyst")
