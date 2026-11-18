"""Descubrir vacantes en la búsqueda PÚBLICA de Computrabajo Colombia (sin sesión), con pocas peticiones y pausas.

Formas verificadas (2026-11-18): `/trabajo-de-<cargo>[-en-<ciudad>|-en-remoto]?pubdate=<días>&by=publicationtime&p=<n>`,
20 ofertas por página. Cuando una ciudad tiene pocas, Computrabajo completa con otras ciudades. La oferta completa
también es pública; las «Palabras clave» del final se descartan (son para el buscador y confunden el análisis).
"""

import html
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

from runner import (
    discover as linkedin,  # comparte la identidad del navegador, el error de bloqueo y las pausas
)
from runner.config import Search
from runner.discover import UA, BlockedError

BASE = "https://co.computrabajo.com"
PAGE_SIZE = 20
PREFIX = "ct:"  # en el estado del bot, para no mezclarlas con las de LinkedIn
# Ciudades con un nombre distinto en las direcciones de Computrabajo; las demás se escriben tal cual («medellin»).
PLACES = {"colombia": "", "remoto": "remoto", "cartagena": "cartagena-de-indias", "bogota": "bogota-dc",
          "bogota dc": "bogota-dc", "bogota d.c.": "bogota-dc"}
DAYS = (1, 3, 7, 15, 30)


@dataclass(frozen=True)
class Card:
    job_id: str  # «ct:» + el código de la oferta
    title: str
    company: str
    place: str
    posted: date | None
    url: str  # la forma canónica que guarda la app (sin el «#lc=…» del listado)


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def place_slug(place: str) -> str:
    key = re.sub(r"\s+", " ", unicodedata.normalize("NFKD", place.strip().lower()).encode("ascii", "ignore").decode())
    key = key.split(",")[0].strip()  # «Medellín, Antioquia» → «medellin»
    return PLACES[key] if key in PLACES else slug(key)


def search_url(search: Search, page: int = 1) -> str:
    where = place_slug(search.place)
    days = min((d for d in DAYS if d >= search.days), default=30)
    url = f"{BASE}/trabajo-de-{slug(search.keywords)}" + (f"-en-{where}" if where else "")
    return url + f"?pubdate={days}&by=publicationtime" + (f"&p={page}" if page > 1 else "")


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _posted(text: str, today: date) -> date | None:
    t = text.lower()
    if re.search(r"\b(minuto|hora)s?\b", t) or "hoy" in t:
        return today
    if "ayer" in t:
        return today - timedelta(days=1)
    if match := re.search(r"hace\s+(\d+)\s+d[ií]as?", t):
        return today - timedelta(days=int(match.group(1)))
    return None


def parse_cards(page: str, *, today: date | None = None) -> list[Card]:
    today = today or date.today()
    cards, seen = [], set()
    for chunk in re.split(r"<article\b", page)[1:]:
        chunk = chunk.split("</article>")[0]
        code = re.search(r"data-id='([0-9A-F]{16,})'", chunk)
        link = re.search(r'class="js-o-link[^"]*"\s+href="(/ofertas-de-trabajo/[^"#?]+)[^"]*"[^>]*>(.*?)</a>', chunk, re.S)
        if not code or not link or code.group(1) in seen:
            continue
        seen.add(code.group(1))
        company = re.search(r"offer-grid-article-company-url[^>]*>(.*?)</a>", chunk, re.S)
        place = re.search(r'<p class="fs16 fc_base mt5">\s*<span class="mr10">(.*?)</span>', chunk, re.S)
        when = re.findall(r'<p class="fs13 fc_aux[^"]*">(.*?)</p>', chunk, re.S)
        cards.append(Card(
            job_id=PREFIX + code.group(1),
            title=_text(link.group(2)),
            company=_text(company.group(1)) if company else "",
            place=_text(place.group(1)) if place else "",
            posted=_posted(_text(when[-1]), today) if when else None,
            url=BASE + link.group(1),
        ))
    return cards


def parse_posting(page: str) -> str:
    """Texto de la oferta (condiciones, descripción, requisitos y aptitudes), listo para el motor."""
    start = page.find('div-link="oferta"')
    if start < 0:
        return ""
    block = page[start:]
    end = min((i for i in (block.find("Palabras clave"), block.find("data-href-offer-apply")) if i > 0), default=len(block))
    block = block[:end]
    tags = [_text(t) for t in re.findall(r'<span class="tag base[^"]*">(.*?)</span>', block, re.S)]
    body = re.search(r'<p class="mbB">(.*?)</p>', block, re.S)
    lines = []
    if body:
        raw = re.sub(r"<\s*br\s*/?>", "\n", body.group(1), flags=re.I)
        lines = [html.unescape(re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "", line))).strip() for line in raw.split("\n")]
    text = "\n".join(line for line in lines if line)
    requirements = [_text(li) for li in re.findall(r"<li[^>]*>(.*?)</li>", block, re.S)]
    skills = [_text(s) for s in re.findall(r"data-skill-id=\"[^\"]*\">(.*?)</span>", block, re.S)]
    parts = [" · ".join(tags), text]
    if requirements:
        parts.append("Requerimientos:\n" + "\n".join(f"- {r}" for r in requirements))
    if skills:
        parts.append("Aptitudes: " + ", ".join(skills))
    return "\n\n".join(p for p in parts if p).strip()


def fetch(url: str, *, timeout: float = 25) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9,en;q=0.6"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            page = response.read(3_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429, 503):
            raise BlockedError(f"Computrabajo frenó las peticiones (HTTP {e.code}). Espera unas horas.") from None
        raise
    if "cf_chl_opt" in page or "<title>Just a moment" in page:  # página de verificación de Cloudflare: no se resuelve
        raise BlockedError("Computrabajo pidió una verificación de navegador. Espera unas horas.")
    return page


def posting_text(card: Card) -> str:
    return parse_posting(fetch(card.url))


def discover(search: Search, *, pages: int = 2) -> list[Card]:
    cards: list[Card] = []
    for page in range(1, pages + 1):
        found = parse_cards(fetch(search_url(search, page)))
        cards.extend(c for c in found if c.job_id not in {x.job_id for x in cards})
        if len(found) < PAGE_SIZE:
            break
        linkedin.pause()
    return cards
