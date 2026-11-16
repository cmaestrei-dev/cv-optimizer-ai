"""Descubrir vacantes en la búsqueda PÚBLICA de LinkedIn (sin sesión), con pocas peticiones y pausas.

Desde septiembre de 2026, con sesión iniciada LinkedIn usa una búsqueda con IA que ignora los filtros de
la URL; la vista pública sí respeta la fecha (f_TPR) y la «Solicitud sencilla» (f_AL). Leer la oferta
también es público: así la sesión de la persona solo se usa para postular.
"""

import html
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date

from runner.config import Search

BASE = "https://www.linkedin.com/jobs-guest/jobs/api"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
PAGE_SIZE = 10


class BlockedError(RuntimeError):
    """LinkedIn está frenando las peticiones (429/999): hay que parar y esperar."""


@dataclass(frozen=True)
class Card:
    job_id: str
    title: str
    company: str
    place: str
    posted: date | None

    @property
    def url(self) -> str:
        return f"https://www.linkedin.com/jobs/view/{self.job_id}"  # la forma canónica que guarda la app


def search_url(search: Search, start: int = 0) -> str:
    params = {"keywords": search.keywords, "geoId": search.geo_id, "f_TPR": f"r{search.days * 86400}", "start": str(start)}
    if search.easy_apply:
        params["f_AL"] = "true"
    return f"{BASE}/seeMoreJobPostings/search?{urllib.parse.urlencode(params)}"


def posting_url(job_id: str) -> str:
    return f"{BASE}/jobPosting/{job_id}"


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _first(pattern: str, source: str) -> str:
    match = re.search(pattern, source, re.S)
    return _text(match.group(1)) if match else ""


def parse_cards(page: str) -> list[Card]:
    cards, seen = [], set()
    for chunk in re.split(r"<li[\s>]", page)[1:]:
        match = re.search(r"jobPosting:(\d+)", chunk)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        when = re.search(r'<time[^>]*datetime="(\d{4}-\d{2}-\d{2})"', chunk)
        try:
            posted = date.fromisoformat(when.group(1)) if when else None
        except ValueError:
            posted = None
        cards.append(Card(
            job_id=match.group(1),
            title=_first(r'base-search-card__title[^>]*>(.*?)</', chunk),
            company=_first(r'base-search-card__subtitle[^>]*>(.*?)</h4>', chunk),
            place=_first(r'job-search-card__location[^>]*>(.*?)</', chunk),
            posted=posted,
        ))
    return cards


def parse_posting(page: str) -> str:
    """Texto de la oferta (descripción y criterios), listo para el motor."""
    match = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page, re.S)
    if not match:
        return ""
    body = match.group(1)
    body = re.sub(r"<\s*(br|/p|/li|/h\d)\s*/?>", "\n", body, flags=re.I)
    body = re.sub(r"<\s*li[^>]*>", "\n- ", body, flags=re.I)
    lines = [html.unescape(re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "", line))).strip() for line in body.split("\n")]
    text = "\n".join(line for line in lines if line)
    criteria = re.findall(r'description__job-criteria-subheader">\s*(.*?)\s*<.*?description__job-criteria-text[^>]*>\s*(.*?)\s*<', page, re.S)
    if criteria:
        text += "\n\n" + "\n".join(f"{_text(k)}: {_text(v)}" for k, v in criteria)
    return text


def fetch(url: str, *, timeout: float = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9,en;q=0.6"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(3_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (429, 999):
            raise BlockedError(f"LinkedIn frenó las peticiones (HTTP {e.code}). Espera unas horas.") from None
        raise


def pause(low: float = 2.5, high: float = 5.0) -> None:
    time.sleep(random.uniform(low, high))


def discover(search: Search, *, pages: int = 2) -> list[Card]:
    cards: list[Card] = []
    for page in range(pages):
        found = parse_cards(fetch(search_url(search, page * PAGE_SIZE)))
        cards.extend(c for c in found if c.job_id not in {x.job_id for x in cards})
        if len(found) < PAGE_SIZE:
            break
        pause()
    return cards
