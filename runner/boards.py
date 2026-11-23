"""Vigilar portales de empleo de empresas en sistemas con API pública de ofertas (sin sesión): Recruitee, Greenhouse,
Lever, Ashby y SmartRecruiters. Un mismo módulo sirve para todas las empresas que usan cada sistema.

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
Postular en esos formularios suele tener captcha o pedir cuenta: el bot no postula; la oferta llega por Telegram.
"""

import html
import re
import urllib.parse
from collections.abc import Callable
from datetime import date, datetime

from runner import watch

PORTALS = ("recruitee", "greenhouse", "lever", "ashby", "smartrecruiters")
# La página pública de cada sistema para una cuenta (cuando la configuración no trae `sitio`)
PUBLIC = {"greenhouse": "https://job-boards.greenhouse.io/{}", "lever": "https://jobs.lever.co/{}",
          "ashby": "https://jobs.ashbyhq.com/{}", "smartrecruiters": "https://jobs.smartrecruiters.com/{}"}

GetJson = Callable[[str], dict]


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


def listing(site, *, get: GetJson | None = None) -> list[tuple[str, str, str]]:
    """(id, cargo, enlace público) de las ofertas del país en el portal de la empresa."""
    if site.portal != "recruitee" and not site.account:
        raise ValueError(f"[[vigilar]] de {site.portal} necesita «cuenta»")
    if site.portal == "smartrecruiters" and not _code(site.country):
        raise ValueError(f"no conozco el código del país «{site.country}»")
    return globals()[f"_{site.portal}_listing"](site, _get(get))


def posting(site, url: str, *, get: GetJson | None = None) -> dict:
    """Cargo, lugar, texto, fechas y empresa de una oferta."""
    return globals()[f"_{site.portal}_posting"](site, url, _get(get))
