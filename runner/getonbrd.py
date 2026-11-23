"""Vigilar Get on Board (empleos de tecnología en Latinoamérica) con su API pública, sin sesión.

Verificado (2026-11-22):
- `GET https://www.getonbrd.com/api/v0/search/jobs?query=<texto>&country_code=<CO>&per_page=100&page=<n>` (sin clave)
  trae las ofertas abiertas al país (presenciales, híbridas y remotas para quien vive allí): cargo, categoría, nivel
  (`seniority`: 1 sin experiencia, 2 junior, 3 semi senior, 4 senior, 5 expert), idioma (`lang`), países,
  `published_at` y el enlace público. Para Colombia: 132 ofertas, 3 de tecnología junior o sin experiencia.
- El detalle por la API (`/api/v0/jobs/<id>`) pide clave; la página pública de la oferta trae schema.org JobPosting
  en microdatos (title, datePosted, addressLocality, description y la empresa en hiringOrganization).
- Postular pide cuenta en Get on Board (Google, LinkedIn, GitHub o correo): el bot no postula; llega por Telegram.
"""

import html
import re
import urllib.parse
from collections.abc import Callable
from datetime import date, datetime

from runner import watch

COUNTRY_CODES = {"colombia": "CO", "chile": "CL", "peru": "PE", "mexico": "MX", "argentina": "AR", "uruguay": "UY",
                 "ecuador": "EC", "venezuela": "VE", "bolivia": "BO", "paraguay": "PY", "costa rica": "CR"}
TECH = ("programming", "sysadmin", "devops", "qa", "cyber", "data", "mobile", "technical support", "machine learning")
LEVELS = {1, 2, 3}  # sin experiencia, junior y semi senior (la compatibilidad de la app decide)
MAX_AGE_DAYS = 30
MAX_PAGES = 5

GetJson = Callable[[str], dict]


def country_code(country: str) -> str:
    code = COUNTRY_CODES.get(watch._norm(country).strip(), "")
    if not code:
        raise ValueError(f"Get on Board: no conozco el país «{country}»")
    return code


def _keep(job: dict, country: str, today: date) -> bool:
    a = job.get("attributes") or {}
    try:
        level = int(((a.get("seniority") or {}).get("data") or {}).get("id"))
    except (TypeError, ValueError):
        return False
    if level not in LEVELS or not any(t in str(a.get("category_name") or "").lower() for t in TECH):
        return False
    if a.get("lang") == "en" and country not in (a.get("countries") or []):
        return False  # en inglés y no es de una sede en el país (decisión del dueño: su inglés es básico)
    published = a.get("published_at")
    return isinstance(published, int | float) and (today - date.fromtimestamp(published)).days <= MAX_AGE_DAYS


def listing(site, *, get: GetJson | None = None, today: date | None = None) -> list[tuple[str, str, str]]:
    """(id, cargo, enlace público) de las ofertas de tecnología recientes, de nivel junior o semi senior."""
    get, today = get or watch.request_json, today or date.today()
    code = country_code(site.country)
    out, seen = [], set()
    for term in site.terms or [""]:
        for page in range(1, MAX_PAGES + 1):
            params = {"query": term, "country_code": code, "per_page": 100, "page": page}
            data = get(f"{site.base}/api/v0/search/jobs?" + urllib.parse.urlencode(params))
            for job in data.get("data") or []:
                job_id, link = str(job.get("id") or ""), (job.get("links") or {}).get("public_url", "")
                if job_id and link and job_id not in seen and _keep(job, site.country, today):
                    seen.add(job_id)
                    out.append((job_id, str(job["attributes"].get("title") or "").strip(), link))
            if page >= int((data.get("meta") or {}).get("total_pages") or 1):
                break
            watch.pause(1.5, 3)
    return out


def _prop(page: str, name: str) -> str:
    match = re.search(r'<(\w+)[^>]*itemprop="' + name + r'"[^>]*>([^<]*)<', page)
    return html.unescape(match.group(2)).strip() if match else ""


def _attr(page: str, name: str, attr: str) -> str:
    match = re.search(r'<[^>]*itemprop="' + name + r'"[^>]*>', page)
    found = re.search(attr + r'="([^"]*)"', match.group(0)) if match else None
    return html.unescape(found.group(1)).strip() if found else ""


def parse_posting(page: str) -> dict:
    start = page.find('itemprop="description"')
    body = watch._element(page, page.rfind("<", 0, start), "div") if start >= 0 else ""
    org = page.find('itemprop="hiringOrganization"')
    company = re.search(r'alt="([^"]+)"', page[org:org + 1500]) if org >= 0 else None
    try:
        posted = datetime.fromisoformat(_attr(page, "datePosted", "datetime")).date()
    except ValueError:
        posted = None
    place = ", ".join(p for p in (_attr(page, "addressLocality", "content"), _attr(page, "addressCountry", "content")) if p)
    return {"title": _prop(page, "title"), "place": place, "text": watch.html_text(body), "posted": posted,
            "closes": None, "company": html.unescape(company.group(1)).strip() if company else ""}


def posting(site, url: str) -> dict:
    """Cargo, empresa, lugar, texto y fecha de la página pública de la oferta."""
    return parse_posting(watch.fetch(url))
