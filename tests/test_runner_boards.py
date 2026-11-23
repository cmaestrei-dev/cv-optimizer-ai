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


TEAMTAILOR = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:tt="https://teamtailor.com/locations"><channel><title>Periferia IT </title>
<item><title>Analista Soporte de Aplicaciones – SQL</title>
<description>&lt;p&gt;Soporte a aplicaciones&lt;/p&gt;&lt;ul&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;/ul&gt;</description>
<pubDate>Wed, 18 Nov 2026 10:00:00 -0500</pubDate><link>https://jobs.periferiaitgroup.com/jobs/1-analista-soporte</link>
<guid>977e15a5</guid><tt:locations><tt:location><tt:city>Bogotá</tt:city><tt:country>Colombia</tt:country></tt:location></tt:locations></item>
<item><title>Desarrollador Java</title><description>x</description><link>https://jobs.periferiaitgroup.com/jobs/2-java</link>
<guid>abc</guid><tt:locations><tt:location><tt:city>Lima</tt:city><tt:country>Perú</tt:country></tt:location></tt:locations></item>
</channel></rss>"""


def test_teamtailor(monkeypatch):
    s = site("teamtailor", base="https://periferiait.teamtailor.com")
    monkeypatch.setattr(watch, "fetch", lambda url: TEAMTAILOR if url == "https://periferiait.teamtailor.com/jobs.rss" else pytest.fail(url))
    assert boards.listing(s) == [("977e15a5", "Analista Soporte de Aplicaciones – SQL", "https://jobs.periferiaitgroup.com/jobs/1-analista-soporte")]
    info = boards.posting(s, "https://jobs.periferiaitgroup.com/jobs/1-analista-soporte")
    assert info["text"] == "Soporte a aplicaciones\n- SQL" and info["place"] == "Bogotá, Colombia"
    assert info["company"] == "Periferia IT" and str(info["posted"]) == "2026-11-18"


BUK_LIST = """<div class="jobs__card"><b class="fw-700 line-height-5 font-size-16">Estudiante de Plataformas y Disponibilidad</b>
<a class="btn" href="https://lapipolnequi.buk.co/s/AAjHsL6K4xLCVpAr">Ver Empleo</a></div>
<div class="jobs__card"><b class="fw-700 line-height-5 font-size-16">Banco de Talentos Dirección de Riesgos</b>
<a class="btn" href="https://lapipolnequi.buk.co/s/ZCDEddHAyPLSymiU">Ver Empleo</a></div>"""
BUK_JOB = """<script type="application/ld+json" nonce="x">{"@context": "https://schema.org/", "@type": "JobPosting",
"title": "Estudiante de Plataformas y Disponibilidad", "description": "Apoyar al equipo de infraestructura.\\n1. Servicios en AWS",
"datePosted": "2026-11-10 18:34:38 -0300", "hiringOrganization": {"@type": "Organization", "name": "NEQUI SA"},
"jobLocation": {"@type": "Place", "address": {"addressLocality": "Medellín, Antioquia", "addressCountry": "CO"}}}</script>"""


def test_buk(monkeypatch):
    s = site("buk", base="https://lapipolnequi.buk.co")
    pages = {"https://lapipolnequi.buk.co/trabaja-con-nosotros": BUK_LIST, "https://lapipolnequi.buk.co/s/AAjHsL6K4xLCVpAr": BUK_JOB}
    monkeypatch.setattr(watch, "fetch", lambda url: pages[url])
    rows = boards.listing(s)
    assert [r[0] for r in rows] == ["AAjHsL6K4xLCVpAr", "ZCDEddHAyPLSymiU"]
    assert watch.matches(s, rows[0][1]) and not watch.matches(s, rows[1][1])  # la práctica de TI sí; «Riesgos» no
    info = boards.posting(s, rows[0][2])
    assert info["text"] == "Apoyar al equipo de infraestructura.\n1. Servicios en AWS" and info["company"] == "NEQUI SA"
    assert info["place"] == "Medellín, Antioquia, CO" and str(info["posted"]) == "2026-11-10"


def _next(props: dict) -> str:
    import json as _json
    return f'<script id="__NEXT_DATA__" type="application/json">{_json.dumps({"props": {"pageProps": props}})}</script>'


def test_gupy(monkeypatch):
    s = site("gupy", base="https://stefaninilatam.gupy.io")
    jobs = [{"id": 12856947, "title": "Help Desk Analyst L1", "workplace": {"address": {"country": "Colômbia"}}},
            {"id": 12883011, "title": "Analista de Infraestructura", "workplace": {"address": {"country": "Peru"}}}]
    job = {"name": "Help Desk Analyst L1", "description": "<p>Soporte N1</p>", "responsibilities": "<ul><li>Tickets</li></ul>",
           "prerequisites": "<ul><li>Técnico en sistemas</li></ul>", "publishedAt": "2026-11-10T15:00:00.000Z",
           "registerEndDate": "2027-01-05T00:00:00.000Z", "addressCity": "Bogotá, D.C.", "addressCountry": "Colômbia"}
    pages = {"https://stefaninilatam.gupy.io/": _next({"jobs": jobs}), "https://stefaninilatam.gupy.io/jobs/12856947": _next({"job": job})}
    monkeypatch.setattr(watch, "fetch", lambda url: pages[url])
    assert boards.listing(s) == [("12856947", "Help Desk Analyst L1", "https://stefaninilatam.gupy.io/jobs/12856947")]
    info = boards.posting(s, "https://stefaninilatam.gupy.io/jobs/12856947")
    assert info["text"] == "Soporte N1\n- Tickets\n- Técnico en sistemas" and str(info["closes"]) == "2027-01-05"


def test_muevete_downloads_the_big_list_once_per_round():
    s = site("muevete", base="https://ftc.falabella.tech/bff-sgdt-job-offer/api/ofertalaboral/type/external")
    offers = [{"offer_id": "1", "title": "Practicante Area de Sistemas", "url": "https://falabella.airavirtual.com/postula/a",
               "country": "Colombia", "city": "Bogotá, D.C.", "date": "2026-11-18T10:00:00.000Z", "vigencia": "1",
               "description": "Apoyar a TI.\nSoporte", "requirements": "-Estudiante de sistemas<br/>-Excel", "company": "Banco Falabella",
               "requisition_company": "Banco Falabella Colombia"},
              {"offer_id": "2", "title": "Cajero", "url": "https://falabella.airavirtual.com/postula/b", "country": "Chile", "vigencia": "1"},
              {"offer_id": "3", "title": "Soporte IT", "url": "https://falabella.airavirtual.com/postula/c", "country": "Colombia", "vigencia": "0"}]
    get = router({s.base: offers})
    assert boards.listing(s, get=get) == [("1", "Practicante Area de Sistemas", "https://falabella.airavirtual.com/postula/a")]
    info = boards.posting(s, "https://falabella.airavirtual.com/postula/a", get=get)
    assert info["text"] == "Apoyar a TI.\nSoporte\n-Estudiante de sistemas\n-Excel" and info["company"] == "Banco Falabella Colombia"
    assert len(get.calls) == 1  # la lista (6 MB) se bajó una sola vez


def test_workday_portals_take_turns(monkeypatch):
    names = [f"W{i}" for i in range(5)]
    sites = [watch.Site(name=n, base=f"https://{n.lower()}.wd1.myworkdayjobs.com/C", terms=[], portal="workday", country="Colombia")
             for n in names]
    seen = []
    monkeypatch.setattr(watch, "listing", lambda s, get=None: seen.append(s.name) or [])
    data = {}
    watch.check(sites, data)
    watch.check(sites, data)
    assert seen[:3] == ["W0", "W1", "W2"] and set(seen[3:]) == {"W3", "W4", "W0"}  # de a 3 por vuelta, primero los olvidados
