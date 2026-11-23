"""Vigilar portales de empleo de empresas en sistemas con lista pública de ofertas (sin sesión): Recruitee, Greenhouse,
Lever, Ashby, SmartRecruiters, Teamtailor, Buk y Gupy, más Muévete (Grupo Falabella). Un mismo módulo sirve para
todas las empresas de cada sistema.

Verificado (2026-11-22), con la empresa de ejemplo:
- Recruitee (Bold): `GET <sitio>/api/offers/` → `offers` (id, title, careers_url, country_code, locations,
  description y requirements en HTML, published_at, close_at, company_name).
- Greenhouse (Clara): `GET boards-api.greenhouse.io/v1/boards/<cuenta>/jobs` → `jobs` (id, title, location.name,
  absolute_url); `…/jobs/<id>` trae `content` (HTML escapado), first_published y application_deadline.
- Lever (Yuno): `GET api.lever.co/v0/postings/<cuenta>?mode=json` → lista (id, text, categories.location, country
  ISO, hostedUrl, createdAt en ms); `…/<id>?mode=json` trae descriptionPlain, lists y additionalPlain.
- Ashby (Addi): `GET api.ashbyhq.com/posting-api/job-board/<cuenta>` → `jobs` (id, title, location,
  secondaryLocations, address.postalAddress.addressCountry, jobUrl, descriptionHtml, publishedAt).
- SmartRecruiters (Experian): `GET api.smartrecruiters.com/v1/companies/<cuenta>/postings?country=co` → `content`
  (id, name, location, releasedDate); `…/postings/<id>` trae jobAd.sections (HTML) y postingUrl.
- Teamtailor (Periferia IT, Alegra, Siigo, Bluetab): `GET <sitio>/jobs.rss` → `<item>` con title, link, pubDate,
  description (HTML escapado) y `tt:locations` (`tt:city`, `tt:country`); el canal trae el nombre de la empresa.
- Buk (Nequi, Ceiba, LINQ): `<sitio>/trabaja-con-nosotros` lista tarjetas (`<b class="fw-700…">cargo</b>` y el enlace
  `<sitio>/s/<código>`); el enlace lleva a la oferta, que trae schema.org JobPosting en JSON-LD (descripción,
  datePosted, addressLocality, addressCountry y la empresa). La lista no dice el país: cada portal es de una empresa.
- Gupy (Stefanini): `<sitio>/` trae `__NEXT_DATA__` con `jobs` (id, title, workplace.address.country: «Colômbia»);
  `<sitio>/jobs/<id>` trae `job` (description, responsibilities, prerequisites, publishedAt, registerEndDate).
- Muévete (Grupo Falabella: banco, tiendas, seguros): `GET <sitio>` (`…/bff-sgdt-job-offer/api/ofertalaboral/type/
  external`) trae TODAS las ofertas en una lista (unos 6 MB; offer_id, title, description, requirements, company, city,
  country, date, url de postulación en AIRA). Se baja una vez por vuelta y se guarda en memoria.
Postular en esos formularios suele tener captcha o pedir cuenta: el bot no postula; la oferta llega por Telegram.
"""

import html
import json
import re
import urllib.parse
from collections.abc import Callable
from datetime import date, datetime
from email.utils import parsedate_to_datetime

from runner import watch

PORTALS = ("recruitee", "greenhouse", "lever", "ashby", "smartrecruiters", "teamtailor", "buk", "gupy", "muevete")
# La página pública de cada sistema para una cuenta (cuando la configuración no trae `sitio`)
PUBLIC = {"greenhouse": "https://job-boards.greenhouse.io/{}", "lever": "https://jobs.lever.co/{}",
          "ashby": "https://jobs.ashbyhq.com/{}", "smartrecruiters": "https://jobs.smartrecruiters.com/{}"}

GetJson = Callable[[str], dict]
ACCOUNT_PORTALS = ("greenhouse", "lever", "ashby", "smartrecruiters")


def _get(get: GetJson | None) -> GetJson:
    return get or watch.request_json


def _code(country: str) -> str:
    return watch.COUNTRY_CODES.get(watch._norm(country).strip(), "")


def _here(country: str, *places, codes=()) -> bool:
    """¿Es del país? Por su nombre en algún lugar o por su código ISO."""
    want, code = watch._norm(country).strip(), _code(country)
    return any(want in watch._norm(str(p or "")) for p in places) or bool(code) and code in {str(c or "").upper() for c in codes}


def _day(value) -> date | None:
    if isinstance(value, int | float) and value > 0:
        return date.fromtimestamp(value / 1000 if value > 10**11 else value)
    try:
        return datetime.fromisoformat(str(value or "")[:10]).date()
    except ValueError:
        return None


def _info(title="", place="", body="", posted=None, closes=None, company="") -> dict:
    return {"title": str(title or "").strip(), "place": str(place or "").strip(), "text": watch.html_text(body or ""),
            "posted": _day(posted), "closes": _day(closes), "company": str(company or "").strip()}


# --- Recruitee ---

def _recruitee_offers(site, get) -> list[dict]:
    return get(f"{site.base}/api/offers/").get("offers") or []


def _recruitee_listing(site, get) -> list[tuple[str, str, str]]:
    out = []
    for o in _recruitee_offers(site, get):
        codes = [o.get("country_code"), *((loc or {}).get("country_code") for loc in o.get("locations") or [])]
        if _here(site.country, o.get("country"), o.get("location"), codes=codes) and o.get("careers_url"):
            out.append((str(o["id"]), str(o.get("title") or "").strip(), o["careers_url"]))
    return out


def _recruitee_posting(site, url, get) -> dict:
    o = next((o for o in _recruitee_offers(site, get) if o.get("careers_url") == url), None) or {}
    return _info(o.get("title"), o.get("location"), f"{o.get('description') or ''}<br>{o.get('requirements') or ''}",
                 o.get("published_at"), o.get("close_at"), o.get("company_name"))


# --- Greenhouse ---

_GH = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"


def _greenhouse_listing(site, get) -> list[tuple[str, str, str]]:
    out = []
    for j in get(_GH.format(site.account)).get("jobs") or []:
        places = [(j.get("location") or {}).get("name"), *((o or {}).get("name") for o in j.get("offices") or [])]
        if _here(site.country, *places) and j.get("absolute_url"):
            out.append((str(j["id"]), str(j.get("title") or "").strip(), j["absolute_url"]))
    return out


def _greenhouse_posting(site, url, get) -> dict:
    match = re.search(r"(?:/jobs/|gh_jid=)(\d+)", url)
    if not match:
        return _info()
    j = get(f"{_GH.format(site.account)}/{match.group(1)}")
    return _info(j.get("title"), (j.get("location") or {}).get("name"), html.unescape(j.get("content") or ""),
                 j.get("first_published") or j.get("updated_at"), j.get("application_deadline"), j.get("company_name"))


# --- Lever ---

_LEVER = "https://api.lever.co/v0/postings/{}"


def _lever_listing(site, get) -> list[tuple[str, str, str]]:
    out = []
    data = get(f"{_LEVER.format(site.account)}?mode=json")
    for p in data if isinstance(data, list) else []:
        cats = p.get("categories") or {}
        if _here(site.country, cats.get("location"), *(cats.get("allLocations") or []), codes=[p.get("country")]) \
                and p.get("hostedUrl"):
            out.append((str(p["id"]), str(p.get("text") or "").strip(), p["hostedUrl"]))
    return out


def _lever_posting(site, url, get) -> dict:
    match = re.search(r"/([0-9a-f-]{36})", url)
    if not match:
        return _info()
    p = get(f"{_LEVER.format(site.account)}/{match.group(1)}?mode=json")
    lists = "".join(f"<h3>{html.escape(item.get('text') or '')}</h3><ul>{item.get('content') or ''}</ul>"
                    for item in p.get("lists") or [])
    body = f"{p.get('description') or ''}{lists}{p.get('additional') or ''}"
    return _info(p.get("text"), (p.get("categories") or {}).get("location"), body, p.get("createdAt"))


# --- Ashby ---

_ASHBY = "https://api.ashbyhq.com/posting-api/job-board/{}?includeCompensation=false"


def _ashby_jobs(site, get) -> list[dict]:
    return get(_ASHBY.format(site.account)).get("jobs") or []


def _ashby_listing(site, get) -> list[tuple[str, str, str]]:
    out = []
    for j in _ashby_jobs(site, get):
        address = ((j.get("address") or {}).get("postalAddress") or {})
        places = [j.get("location"), address.get("addressCountry"),
                  *((s or {}).get("location") for s in j.get("secondaryLocations") or [])]
        if j.get("isListed", True) and _here(site.country, *places, codes=[address.get("addressCountry")]) and j.get("jobUrl"):
            out.append((str(j["id"]), str(j.get("title") or "").strip(), j["jobUrl"]))
    return out


def _ashby_posting(site, url, get) -> dict:
    j = next((j for j in _ashby_jobs(site, get) if j.get("jobUrl") == url), None) or {}
    return _info(j.get("title"), j.get("location"), j.get("descriptionHtml"), j.get("publishedAt"), company=site.name)


# --- SmartRecruiters ---

_SR = "https://api.smartrecruiters.com/v1/companies/{}/postings"


def _smartrecruiters_listing(site, get) -> list[tuple[str, str, str]]:
    out, offset = [], 0
    for _ in range(5):
        params = {"country": _code(site.country).lower(), "limit": 100, "offset": offset}
        data = get(f"{_SR.format(site.account)}?" + urllib.parse.urlencode(params))
        jobs = data.get("content") or []
        for j in jobs:
            out.append((str(j["id"]), str(j.get("name") or "").strip(),
                        f"{PUBLIC['smartrecruiters'].format(site.account)}/{j['id']}"))
        offset += len(jobs)
        if not jobs or offset >= int(data.get("totalFound") or 0):
            break
        watch.pause(1, 2)
    return out


def _smartrecruiters_posting(site, url, get) -> dict:
    match = re.search(r"/(\d{6,})", url)
    if not match:
        return _info()
    j = get(f"{_SR.format(site.account)}/{match.group(1)}")
    sections = ((j.get("jobAd") or {}).get("sections") or {})
    body = "".join(f"<h3>{html.escape(s.get('title') or '')}</h3>{s.get('text') or ''}" for s in sections.values()
                   if isinstance(s, dict) and s.get("text"))
    return _info(j.get("name"), (j.get("location") or {}).get("fullLocation"), body, j.get("releasedDate"),
                 company=(j.get("company") or {}).get("name"))


# --- Teamtailor ---

def _tag(block: str, name: str) -> str:
    match = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
    return html.unescape(re.sub(r"^<!\[CDATA\[|\]\]>$", "", match.group(1).strip())) if match else ""


def _teamtailor_items(site) -> tuple[str, list[str]]:
    feed = watch.fetch(f"{site.base}/jobs.rss")
    channel = feed.split("<item>", 1)[0]
    return _tag(channel, "title"), re.findall(r"<item>(.*?)</item>", feed, re.S)


def _teamtailor_listing(site, get) -> list[tuple[str, str, str]]:
    out = []
    for item in _teamtailor_items(site)[1]:
        countries = re.findall(r"<tt:country>(.*?)</tt:country>", item)
        if _here(site.country, *countries) and _tag(item, "link"):
            out.append((_tag(item, "guid") or _tag(item, "link"), _tag(item, "title"), _tag(item, "link")))
    return out


def _teamtailor_posting(site, url, get) -> dict:
    company, items = _teamtailor_items(site)
    item = next((i for i in items if _tag(i, "link") == url), "")
    try:
        posted = parsedate_to_datetime(_tag(item, "pubDate")).date().isoformat() if item else None
    except (TypeError, ValueError):
        posted = None
    place = ", ".join(p for p in (_tag(item, "tt:city"), _tag(item, "tt:country")) if p)
    return _info(_tag(item, "title"), place, _tag(item, "description"), posted, company=company)


# --- Buk ---

_BUK_CARD = re.compile(r'<b class="fw-700[^"]*">([^<]+)</b>.*?href="(https?://[^"]+/s/([A-Za-z0-9]+))"', re.S)


def _buk_listing(site, get) -> list[tuple[str, str, str]]:
    page = watch.fetch(f"{site.base}/trabaja-con-nosotros")
    seen, out = set(), []
    for title, url, code in _BUK_CARD.findall(page):
        if code not in seen:
            seen.add(code)
            out.append((code, html.unescape(title).strip(), url))
    return out


def _json_ld(page: str, kind: str) -> dict:
    for raw in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == kind:
            return data
    return {}


def _buk_posting(site, url, get) -> dict:
    job = _json_ld(watch.fetch(url), "JobPosting")
    address = ((job.get("jobLocation") or {}).get("address") or {})
    place = ", ".join(p for p in (address.get("addressLocality"), address.get("addressCountry")) if p)
    body = str(job.get("description") or "").replace("\n", "<br>")
    return _info(job.get("title"), place, body, job.get("datePosted"), job.get("validThrough"),
                 (job.get("hiringOrganization") or {}).get("name"))


# --- Gupy ---

def _next_data(page: str) -> dict:
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    try:
        return ((json.loads(match.group(1)) if match else {}).get("props") or {}).get("pageProps") or {}
    except ValueError:
        return {}


def _gupy_listing(site, get) -> list[tuple[str, str, str]]:
    out = []
    for job in _next_data(watch.fetch(f"{site.base}/")).get("jobs") or []:
        country = (((job.get("workplace") or {}).get("address")) or {}).get("country")
        if job.get("id") and _here(site.country, country):
            out.append((str(job["id"]), str(job.get("title") or "").strip(), f"{site.base}/jobs/{job['id']}"))
    return out


def _gupy_posting(site, url, get) -> dict:
    job = _next_data(watch.fetch(url)).get("job") or {}
    body = "".join(str(job.get(k) or "") for k in ("description", "responsibilities", "prerequisites", "relevantExperiences"))
    place = ", ".join(p for p in (job.get("addressCity"), job.get("addressCountry")) if p)
    company = (job.get("company") or {}).get("name") if isinstance(job.get("company"), dict) else ""
    return _info(job.get("name"), place, body, job.get("publishedAt"), job.get("registerEndDate") or job.get("expiresAt"),
                 company or site.name)


# --- Muévete (Grupo Falabella) ---

_MUEVETE: dict[str, list[dict]] = {}  # sitio → ofertas de esta vuelta (la lista completa pesa unos 6 MB)


def _muevete_offers(site, get) -> list[dict]:
    if site.base not in _MUEVETE:
        data = get(site.base)
        _MUEVETE[site.base] = data if isinstance(data, list) else []
    return _MUEVETE[site.base]


def _muevete_listing(site, get) -> list[tuple[str, str, str]]:
    _MUEVETE.pop(site.base, None)  # una vuelta nueva: lista nueva
    return [(str(o["offer_id"]), str(o.get("title") or "").strip(), o["url"]) for o in _muevete_offers(site, get)
            if o.get("offer_id") and o.get("url") and str(o.get("vigencia", "1")) == "1" and _here(site.country, o.get("country"))]


def _muevete_posting(site, url, get) -> dict:
    o = next((o for o in _muevete_offers(site, get) if o.get("url") == url), None) or {}
    body = f"{html.escape(str(o.get('description') or ''))}<br>{o.get('requirements') or ''}".replace("\n", "<br>")
    place = ", ".join(p for p in (o.get("city"), o.get("country")) if p)
    return _info(o.get("title"), place, body, o.get("date"), company=o.get("requisition_company") or o.get("company"))


def listing(site, *, get: GetJson | None = None) -> list[tuple[str, str, str]]:
    """(id, cargo, enlace público) de las ofertas del país en el portal de la empresa."""
    if site.portal in ACCOUNT_PORTALS and not site.account:
        raise ValueError(f"[[vigilar]] de {site.portal} necesita «cuenta»")
    if site.portal == "smartrecruiters" and not _code(site.country):
        raise ValueError(f"no conozco el código del país «{site.country}»")
    return globals()[f"_{site.portal}_listing"](site, _get(get))


def posting(site, url: str, *, get: GetJson | None = None) -> dict:
    """Cargo, lugar, texto, fechas y empresa de una oferta."""
    return globals()[f"_{site.portal}_posting"](site, url, _get(get))
