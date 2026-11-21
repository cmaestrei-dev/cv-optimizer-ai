"""Descubrir vacantes en la búsqueda PÚBLICA de Magneto (sin sesión), con pocas peticiones y pausas.

Verificado (2026-11-21): `GET https://api.magneto365.com/jobs/v1/public/jobs/search` con
`queries[0][field]=all&queries[0][term]=<texto>`, `filters[locations][0]=C47` (Colombia) y `order[field]=_score`
(el único orden que acepta) entrega 20 vacantes por página con la descripción completa, la empresa, las ciudades,
si es remota, la experiencia y la formación pedidas y si tiene cuestionario de filtro. Por eso no hace falta abrir
cada oferta. La oferta está en `www.magneto365.com/co/empleos/<jobSlug>`, y el número final del slug es su id.
"""

import html
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from runner import (
    discover as linkedin,  # comparte la identidad del navegador, el error de bloqueo y las pausas
)
from runner.config import Search
from runner.discover import UA, BlockedError

API = "https://api.magneto365.com/jobs/v1/public/jobs/search"
OFFER = "https://www.magneto365.com/co/empleos/"
PAGE_SIZE = 20
PREFIX = "mg:"  # en el estado del bot, para no mezclarlas con las de otros portales
COLOMBIA = "C47"
ANYWHERE = {"", "colombia", "todo colombia"}


@dataclass(frozen=True)
class Card:
    job_id: str  # «mg:» + el id de la oferta
    title: str
    company: str
    place: str
    posted: date | None
    url: str  # la forma canónica que guarda la app
    text: str = ""  # la oferta completa, ya en texto (la búsqueda la trae)
    questionnaire: bool = False


def _norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", (text or "").lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", plain).strip()


def search_url(search: Search, page: int = 1) -> str:
    params = {
        "device": "desktop",
        "paginator[page]": page,
        "paginator[pageSize]": PAGE_SIZE,
        "filters[locations][0]": COLOMBIA,
        "order[field]": "_score",
        "order[order]": "DESC",
        "queries[0][field]": "all",
        "queries[0][term]": search.keywords,
    }
    return API + "?" + urllib.parse.urlencode(params)


def html_to_text(fragment: str) -> str:
    text = re.sub(r"<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", fragment or "", flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "- ", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _names(items) -> list[str]:
    return [str(i.get("name") if isinstance(i, dict) else i).strip() for i in (items or []) if i]


def posting_text(card: Card) -> str:
    return card.text


def _row_text(row: dict) -> str:
    details = []
    if row.get("isRemote"):
        details.append("Modalidad: remoto")
    if isinstance(contract := row.get("contractType"), str) and contract.strip() and not contract.isdigit():
        details.append(f"Contrato: {contract.strip()}")  # a veces es solo un código: entonces no se pone
    if (months := row.get("experienceMonthsNumber")) is not None:
        details.append(f"Experiencia requerida: {months} meses" if months else "Experiencia requerida: sin experiencia")
    if levels := _names(row.get("educationLevel")):
        details.append("Formación: " + ", ".join(levels))
    if row.get("toAgree"):
        details.append("Salario: a convenir")
    elif low := int(row.get("minSalary") or row.get("salary") or 0):
        high = int(row.get("maxSalary") or 0)
        money = lambda n: f"{n:,}".replace(",", ".")  # noqa: E731
        details.append(f"Salario: {money(low)}" + (f" a {money(high)}" if high > low else ""))
    parts = [" · ".join(details), html_to_text(row.get("description", ""))]
    if skills := _names(row.get("skills")):
        parts.append("Habilidades: " + ", ".join(skills))
    return "\n\n".join(p for p in parts if p).strip()


def _posted(value: str) -> date | None:
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _place_ok(row: dict, place: str) -> bool:
    want = _norm(place).split(",")[0].strip()
    if want in ANYWHERE:
        return True
    if want == "remoto":
        return bool(row.get("isRemote"))
    return bool(row.get("isRemote")) or any(want in _norm(c) for c in row.get("cities") or [])


def parse(data: dict, *, place: str = "Colombia", days: int = 30, today: date | None = None) -> list[Card]:
    """Las vacantes publicadas y postulables de una página de resultados, filtradas por lugar y antigüedad."""
    today = today or date.today()
    cards = []
    for row in data.get("rows") or []:
        if not row.get("id") or not row.get("jobSlug") or row.get("status", "published") != "published":
            continue
        if row.get("canApply") is False or row.get("isApplied"):
            continue
        posted = _posted(row.get("publishDate", ""))
        if posted and posted < today - timedelta(days=days):
            continue
        if not _place_ok(row, place):
            continue
        cities = row.get("cities") or []
        cards.append(Card(
            job_id=f"{PREFIX}{row['id']}",
            title=str(row.get("title", "")).strip(),
            company="Confidencial" if row.get("confidential") else str(row.get("companyName") or "").strip(),
            place=", ".join(cities[:3]) + (" (remoto)" if row.get("isRemote") else ""),
            posted=posted,
            url=OFFER + row["jobSlug"],
            text=_row_text(row),
            questionnaire=bool(row.get("hasPrefilterQuestionnaire")),
        ))
    return cards


def fetch(url: str, *, timeout: float = 25) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                                   "Accept-Language": "es-CO,es;q=0.9"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(5_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429, 503):
            raise BlockedError(f"Magneto frenó las peticiones (HTTP {e.code}). Espera unas horas.") from None
        raise
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise BlockedError("Magneto no devolvió resultados (¿verificación de navegador?). Espera unas horas.") from None


def discover(search: Search, *, pages: int = 2) -> list[Card]:
    cards: list[Card] = []
    for page in range(1, pages + 1):
        data = fetch(search_url(search, page))
        found = parse(data, place=search.place, days=search.days)
        cards.extend(c for c in found if c.job_id not in {x.job_id for x in cards})
        if len(data.get("rows") or []) < PAGE_SIZE:
            break
        linkedin.pause()
    return cards
