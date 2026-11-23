"""Vigilar los portales de empleo propios de algunas empresas y avisar de las vacantes nuevas que encajen.

Esos portales piden una cuenta por empresa, que crea la persona. El bot mira la búsqueda pública, y a las ofertas que
encajan la app las analiza y les hace el CV: le llegan a la persona por Telegram, listas para postular. En
SuccessFactors con `postular = true` las postula el lote (`python -m runner lote <sitio>`).

Portales (`portal` en `[[vigilar]]`): «successfactors» (por defecto: Bancolombia, Ecopetrol), «workday»
(`runner/workday.py`: Accenture, Unisys…) y «eightfold» (`runner/eightfold.py`: Mercado Libre).

Verificado (2026-11-21): `<sitio>/search/?q=<texto>&locale=es_ES` devuelve hasta 25 ofertas en HTML, cada una como
`<a class="jobTitle-link" href="/<marca>/job/<slug>/<id>/">Cargo</a>`.
"""

import html
import json
import random
import re
import time
import tomllib
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from runner import config as cfg
from runner.discover import UA, BlockedError

PORTALS = ("successfactors", "workday", "eightfold")

# Palabras de tecnología en el cargo («Practicante en Tecnología» sí; «Practicante de Ciencias Económicas» no)
DEFAULT_INCLUDE = ["software", "desarroll", "sistemas", "tecnolog", "informatic", "ciberseg", "seguridad informatica",
                   "seguridad de la informacion", "soporte", "ti", "it", "qa", "pruebas", "datos", "programa", "devops",
                   "cloud", "web", "backend", "frontend", "fullstack", "full stack", "developer", "data", "cyber",
                   "security", "support", "mesa de ayuda", "help desk", "redes", "infra", "middleware", "iam",
                   "identidad"]
DEFAULT_EXCLUDE = ["senior", "sr", "lider", "lead", "arquitect", "gerente", "manager", "director", "jefe", "head",
                   "principal", "staff", "expert", "iii", "iv"]
_LINK = re.compile(r'<a[^>]+class="jobTitle-link"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>')


@dataclass(frozen=True)
class Site:
    name: str
    base: str
    terms: list[str]
    include: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE))
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    min_score: int = 60  # compatibilidad mínima para hacerle el CV y mandarla a la persona
    apply: bool = False  # postular con `python -m runner lote <nombre>` (la persona entra; el bot postula)
    login_url: str = ""  # el acceso del portal (career8…loginFlowRequired=true); con sesión lleva al perfil
    signature: str = ""  # nombre completo para aceptar la declaración de conformidad (autorizado por la persona)
    answers: dict[str, str] = field(default_factory=dict)  # respuestas propias del portal (patrón → opción)
    portal: str = "successfactors"
    country: str = ""  # Workday y Eightfold: solo las ofertas de este país («Colombia»)
    domain: str = ""  # Eightfold: el dominio de la empresa («mercadolibre.com»)
    tenant: str = ""  # Workday: si no es la primera parte del dominio («accenture».wd103.myworkdayjobs.com)


def _norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", (text or "").lower()).encode("ascii", "ignore").decode()
    return " " + re.sub(r"\s+", " ", plain).strip() + " "


def load_sites(path: Path | None = None) -> list[Site]:
    """Las entradas `[[vigilar]]` de la configuración (nombre, sitio y qué buscar)."""
    path = path or cfg.CONFIG_FILE
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return []
    sites = []
    for item in raw.get("vigilar", []):
        base = str(item.get("sitio", "")).strip().rstrip("/")
        terms = [str(t).strip() for t in item.get("buscar", []) if str(t).strip()]
        portal = str(item.get("portal", "successfactors")).strip().lower()
        if portal not in PORTALS:
            raise cfg.ConfigError(f"[[vigilar]] «portal» debe ser uno de: {', '.join(PORTALS)}.")
        if not base.startswith("https://") or (portal == "successfactors" and not terms):
            raise cfg.ConfigError("Cada [[vigilar]] necesita «sitio» (https://…) y, en SuccessFactors, al menos una palabra en «buscar».")
        if portal != "successfactors" and not str(item.get("pais", "")).strip():
            raise cfg.ConfigError(f"[[vigilar]] de {portal} necesita «pais» (p. ej., \"Colombia\").")
        if portal == "eightfold" and not str(item.get("dominio", "")).strip():
            raise cfg.ConfigError("[[vigilar]] de eightfold necesita «dominio» (p. ej., \"mercadolibre.com\").")
        if portal != "successfactors" and item.get("postular"):
            raise cfg.ConfigError(f"[[vigilar]] «postular» solo funciona en SuccessFactors (no en {portal}).")
        sites.append(Site(name=str(item.get("nombre") or base), base=base, terms=terms, portal=portal,
                          country=str(item.get("pais", "")).strip(), domain=str(item.get("dominio", "")).strip(),
                          tenant=str(item.get("tenant", "")).strip(),
                          include=[str(w).lower() for w in item.get("incluir", DEFAULT_INCLUDE)],
                          exclude=[str(w).lower() for w in item.get("excluir", DEFAULT_EXCLUDE)],
                          min_score=int(item.get("compatibilidad_minima", 60)), apply=bool(item.get("postular", False)),
                          login_url=str(item.get("acceso", "")).strip(),
                          signature=str(item.get("firma", "")).strip(),
                          answers={str(k): str(v) for k, v in (item.get("respuestas") or {}).items()}))
        if sites[-1].apply and not sites[-1].login_url.startswith("https://"):
            raise cfg.ConfigError(f"[[vigilar]] «{sites[-1].name}» con postular = true necesita «acceso» (https://…).")
    return sites


def search_url(site: Site, term: str) -> str:
    return f"{site.base}/search/?" + urllib.parse.urlencode({"q": term, "locale": "es_ES"})


def parse(page: str, base: str) -> list[tuple[str, str, str]]:
    """(id, cargo, enlace) de cada oferta de una página de resultados de SuccessFactors."""
    out, seen = [], set()
    for href, title in _LINK.findall(page):
        match = re.search(r"/(\d{5,})/?$", href)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        url = href if href.startswith("http") else base + href
        out.append((match.group(1), html.unescape(title).strip(), url))
    return out


def _has(word: str, text: str) -> bool:
    """La palabra al comienzo de una palabra del cargo («desarroll» → «desarrollador»); las cortas, completas («ti»)."""
    w = _norm(word).strip()
    return bool(w) and re.search(r"\b" + re.escape(w) + (r"\b" if len(w) <= 3 else ""), text) is not None


def matches(site: Site, title: str) -> bool:
    t = _norm(title)
    return any(_has(w, t) for w in site.include) and not any(_has(w, t) for w in site.exclude)


def _meta(page: str, prop: str) -> str:
    match = re.search(r'<meta itemprop="' + prop + r'" content="([^"]*)"', page)
    return html.unescape(match.group(1)).strip() if match else ""


def _day(value: str) -> date | None:
    try:  # «Wed Nov 18 00:00:00 UTC 2026»
        return datetime.strptime(value, "%a %b %d %H:%M:%S %Z %Y").date()
    except ValueError:
        return None


def _element(page: str, start: int, tag: str = "span") -> str:
    """El contenido del elemento que abre en `start`, contando las etiquetas anidadas del mismo tipo."""
    depth, i = 0, start
    for match in re.finditer(rf"<(/?){tag}\b[^>]*>", page[start:]):
        depth += -1 if match.group(1) else 1
        if depth == 0:
            i = start + match.end()
            break
    return page[start:i]


def html_text(body: str) -> str:
    """Texto legible de la descripción en HTML de una oferta (párrafos y viñetas en líneas)."""
    body = re.sub(r"<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", body, flags=re.I)
    body = re.sub(r"<\s*li[^>]*>", "- ", body, flags=re.I)
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in html.unescape(re.sub(r"<[^>]+>", " ", body)).split("\n")]
    return "\n".join(line for line in lines if line)


def posting(page: str) -> dict:
    """Cargo, lugar, texto, fecha de publicación y de cierre de una oferta pública de SuccessFactors."""
    title = re.search(r'itemprop="title"[^>]*>([^<]+)<', page)
    start = page.find('<span itemprop="description"')
    body = _element(page, start) if start >= 0 else ""
    return {"title": html.unescape(title.group(1)).strip() if title else "",
            "place": ", ".join(p for p in (_meta(page, "addressLocality"), _meta(page, "addressCountry")) if p),
            "text": html_text(body), "posted": _day(_meta(page, "datePosted")),
            "closes": _day(_meta(page, "validThrough"))}


def read_posting(site: Site, url: str) -> dict:
    """La oferta pública de cualquier portal (ver `posting`)."""
    if site.portal == "workday":
        from runner import workday
        return workday.posting(site, url)
    if site.portal == "eightfold":
        from runner import eightfold
        return eightfold.posting(site, url)
    return posting(fetch(url))


def fetch(url: str, *, timeout: float = 25) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(3_000_000).decode("utf-8", "replace")


def request_json(url: str, body: dict | None = None, *, timeout: float = 25) -> dict:
    """GET (o POST con `body`) a una API pública de empleos. 429/403: el portal está frenando (BlockedError)."""
    headers = {"User-Agent": UA, "Accept": "application/json", "Accept-Language": "es-CO,es;q=0.9"}
    data = None
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read(5_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise BlockedError(f"el portal frenó las peticiones (HTTP {e.code}); se reintenta en la próxima vuelta") from None
        raise


def pause(low: float, high: float) -> None:
    time.sleep(random.uniform(low, high))


def listing(site: Site, *, get: Callable[[str], str] = fetch) -> list[tuple[str, str, str]]:
    """(id, cargo, enlace) de las ofertas publicadas en el portal (SuccessFactors: una búsqueda por palabra)."""
    if site.portal == "workday":
        from runner import workday
        return workday.listing(site)
    if site.portal == "eightfold":
        from runner import eightfold
        return eightfold.listing(site)
    out: list[tuple[str, str, str]] = []
    for term in site.terms:
        try:
            page = get(search_url(site, term))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"{site.name}: no se pudo revisar «{term}» ({str(e)[:80]})")
            continue
        out.extend(parse(page, site.base))
    return out


def check(sites: list[Site], data: dict, *, get: Callable[[str], str] = fetch) -> list[dict]:
    """Revisa los sitios y devuelve las ofertas nuevas que encajan. Anota todas las vistas en `data["vigiladas"]`."""
    seen = data.setdefault("vigiladas", {})
    new = []
    for site in sites:
        try:
            found = listing(site, get=get)
        except (BlockedError, urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            print(f"{site.name}: no se pudo revisar ({str(e)[:100]})")
            continue
        for job_id, title, url in found:
            key = f"{site.name}:{job_id}"
            if key in seen:
                continue
            fit = matches(site, title)
            seen[key] = {"cargo": title, "url": url, "encaja": fit,
                         "cuando": datetime.now(UTC).isoformat(timespec="seconds")}
            if fit:
                new.append({"sitio": site.name, "cargo": title, "url": url})
    return new


def notice(new: list[dict]) -> str:
    rows = [f"· {n['sitio']}: {n['cargo']}\n  {n['url']}" for n in new[:15]]
    more = f"\n… y {len(new) - 15} más" if len(new) > 15 else ""
    return ("Vacantes nuevas en portales de empresas (las que encajan con tu perfil te llegan aparte, con su CV):\n"
            + "\n".join(rows) + more)
