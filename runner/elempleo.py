"""Descubrir vacantes en la búsqueda PÚBLICA de elempleo (sin sesión), con pocas peticiones y pausas.

Formas verificadas (2026-11-21):
- `/co/ofertas-empleo/trabajo-<cargo>[-modalidad-remoto][/<página>]?fecha=<hoy|hace-1-semana|hace-2-semanas|hace-1-mes>`
  da 20 ofertas por página; `fecha=hoy` es «hoy y ayer». Sin `fecha` el orden es por relevancia y mezcla meses.
  La ruta por ciudad (`/cartagena/trabajo-<cargo>`) solo existe para algunos cargos (las demás dan 404): por eso
  se busca en todo el país y se filtra por la ciudad de cada oferta.
- Cada resultado trae en `data-ga4-offerdata` su id, cargo, empresa, ciudad y salario.
- La oferta (`/co/ofertas-trabajo/<slug>-<id>`) es pública y publica schema.org `JobPosting` (descripción, fecha,
  vigencia, ciudad, salario) y `data-jobofferconstraint-val` (experiencia, estudios, contrato, área).
"""

import html
import json
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

BASE = "https://www.elempleo.com"
PAGE_SIZE = 20
PREFIX = "ee:"  # en el estado del bot, para no mezclarlas con las de otros portales
DATES = {1: "hoy", 7: "hace-1-semana", 15: "hace-2-semanas", 30: "hace-1-mes"}
ANYWHERE = {"", "colombia", "todo colombia"}
_CARD = '<div class="col-md-12 result-item mb-3 bg-white"'


@dataclass(frozen=True)
class Card:
    job_id: str  # «ee:» + el número de la oferta
    title: str
    company: str
    place: str
    posted: date | None
    url: str  # la forma canónica que guarda la app


def _norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", (text or "").lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", plain).strip()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _norm(text)).strip("-")


def _remote(place: str) -> bool:
    return _norm(place).split(",")[0].strip() == "remoto"


def search_url(search: Search, page: int = 1) -> str:
    days = min((d for d in DATES if d >= search.days), default=30)
    url = f"{BASE}/co/ofertas-empleo/trabajo-{slug(search.keywords)}" + ("-modalidad-remoto" if _remote(search.place) else "")
    return url + (f"/{page}" if page > 1 else "") + f"?fecha={DATES[days]}"


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _posted(text: str, today: date) -> date | None:
    """La fecha aproximada de «Hoy», «Ayer» o «Hace N días/semanas»; None si no se puede saber."""
    t = _norm(text)
    if t == "hoy" or re.search(r"\b(minuto|hora)s?\b", t):
        return today
    if t == "ayer":
        return today - timedelta(days=1)
    if match := re.search(r"hace (\d+) dias?", t):
        return today - timedelta(days=int(match.group(1)))
    if match := re.search(r"hace (\d+) semanas?", t):
        return today - timedelta(days=7 * int(match.group(1)))
    return None


def _place_ok(card_place: str, modality: str, place: str) -> bool:
    want = _norm(place).split(",")[0].strip()
    if want in ANYWHERE or want == "remoto":  # lo remoto ya viene filtrado por la dirección de la búsqueda
        return True
    return want in _norm(card_place) or "remoto" in _norm(modality)


def parse_cards(page: str, *, place: str = "Colombia", today: date | None = None) -> list[Card]:
    """Las ofertas de una página de resultados, filtradas por la ciudad pedida (o remotas)."""
    today = today or date.today()
    cards, seen = [], set()
    for chunk in page.split(_CARD)[1:]:
        link = re.search(r'data-url="(/co/ofertas-trabajo/[a-z0-9-]+-(\d{6,}))"', chunk)
        data = re.search(r'data-ga4-offerdata="(\{&quot;[^"]*)"', chunk)  # la plantilla vacía no tiene datos
        if not link or not data or link.group(2) in seen:
            continue
        try:
            info = json.loads(html.unescape(data.group(1)))
        except json.JSONDecodeError:
            continue
        seen.add(link.group(2))
        modality = re.search(r'js-work-modality hide">([^<]*)<', chunk)
        when = re.search(r">\s*(Hace [^<]{1,30}|Hoy|Ayer)\s*<", chunk)
        city = str(info.get("location") or "").strip()
        if not _place_ok(city, modality.group(1) if modality else "", place):
            continue
        company = str(info.get("company") or "").strip()
        cards.append(Card(
            job_id=PREFIX + link.group(2),
            title=_text(str(info.get("title") or "")),
            company="Confidencial" if _norm(company) in ("empresa confidencial", "confidential") else company,
            place=city,
            posted=_posted(html.unescape(when.group(1)), today) if when else None,
            url=BASE + link.group(1),
        ))
    return cards


def _posting(page: str) -> dict:
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return {}


def closes_on(page: str) -> date | None:
    try:
        return date.fromisoformat(str(_posting(page).get("validThrough", ""))[:10])
    except ValueError:
        return None


def parse_posting(page: str) -> str:
    """Texto de la oferta (condiciones y descripción), listo para el motor."""
    posting = _posting(page)
    description = str(posting.get("description") or "").replace("\r\n", "\n")
    if not description.strip():
        return ""
    details = []
    raw = re.search(r'data-jobofferconstraint-val="([^"]+)"', page)
    try:
        rules = json.loads(html.unescape(raw.group(1))) if raw else {}
    except json.JSONDecodeError:
        rules = {}
    labels = (("PositionAreas", "Área"), ("PositionLevel", "Nivel"), ("Cities", "Ciudad"), ("Salary", "Salario"),
              ("ContractType", "Contrato"), ("Studylevel", "Formación"))
    for key, label in labels:
        if value := str(rules.get(key) or "").strip():
            details.append(f"{label}: {value}")
    experience = str(rules.get("RequiredExperince") or "").strip()  # así se escribe en elempleo
    if experience.isdigit():
        details.append(f"Experiencia requerida: {experience} años" if int(experience) else "Experiencia requerida: sin experiencia")
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in html.unescape(re.sub(r"<[^>]+>", " ", description)).split("\n")]
    text = "\n".join(line for line in lines if line)
    return "\n\n".join(p for p in (" · ".join(details), text) if p).strip()


def fetch(url: str, *, timeout: float = 25) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9,en;q=0.6"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(3_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429, 503):
            raise BlockedError(f"elempleo frenó las peticiones (HTTP {e.code}). Espera unas horas.") from None
        if e.code in (404, 410):  # búsqueda sin página propia u oferta cerrada
            return ""
        raise


def posting_text(card: Card) -> str:
    page = fetch(card.url)
    ends = closes_on(page)
    if ends and ends < date.today():
        return ""
    return parse_posting(page)


def discover(search: Search, *, pages: int = 2) -> list[Card]:
    cards: list[Card] = []
    for page in range(1, pages + 1):
        raw = fetch(search_url(search, page))
        found = parse_cards(raw, place=search.place)
        cards.extend(c for c in found if c.job_id not in {x.job_id for x in cards})
        if len(set(re.findall(r'data-url="/co/ofertas-trabajo/[a-z0-9-]+-(\d{6,})" data-ga4-offerdata="\{', raw))) < PAGE_SIZE:
            break
        linkedin.pause()
    return cards
