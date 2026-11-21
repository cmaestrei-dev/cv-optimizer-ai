"""Vigilar los portales de empleo propios de algunas empresas y avisar de las vacantes nuevas que encajen.

No postula: esos portales (SAP SuccessFactors, como Bancolombia o Ecopetrol) piden una cuenta por empresa, y la
crea la persona. El bot solo mira la búsqueda pública y avisa (en el registro y por Telegram).

Verificado (2026-11-21): `<sitio>/search/?q=<texto>&locale=es_ES` devuelve hasta 25 ofertas en HTML, cada una como
`<a class="jobTitle-link" href="/<marca>/job/<slug>/<id>/">Cargo</a>`.
"""

import html
import re
import tomllib
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from runner import config as cfg
from runner.discover import UA

# Palabras de tecnología en el cargo («Practicante en Tecnología» sí; «Practicante de Ciencias Económicas» no)
DEFAULT_INCLUDE = ["software", "desarroll", "sistemas", "tecnolog", "informatic", "ciberseg", "seguridad informatica",
                   "soporte", "ti", "it", "qa", "pruebas", "datos", "programa", "devops", "cloud", "web"]
DEFAULT_EXCLUDE = ["senior", "lider", "arquitect", "gerente", "director", "jefe", "iii", "iv"]
_LINK = re.compile(r'<a[^>]+class="jobTitle-link"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>')


@dataclass(frozen=True)
class Site:
    name: str
    base: str
    terms: list[str]
    include: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE))
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))


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
        if not base.startswith("https://") or not terms:
            raise cfg.ConfigError("Cada [[vigilar]] necesita «sitio» (https://…) y al menos una palabra en «buscar».")
        sites.append(Site(name=str(item.get("nombre") or base), base=base, terms=terms,
                          include=[str(w).lower() for w in item.get("incluir", DEFAULT_INCLUDE)],
                          exclude=[str(w).lower() for w in item.get("excluir", DEFAULT_EXCLUDE)]))
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


def fetch(url: str, *, timeout: float = 25) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(3_000_000).decode("utf-8", "replace")


def check(sites: list[Site], data: dict, *, get: Callable[[str], str] = fetch) -> list[dict]:
    """Revisa los sitios y devuelve las ofertas nuevas que encajan. Anota todas las vistas en `data["vigiladas"]`."""
    seen = data.setdefault("vigiladas", {})
    new = []
    for site in sites:
        for term in site.terms:
            try:
                page = get(search_url(site, term))
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                print(f"{site.name}: no se pudo revisar «{term}» ({str(e)[:80]})")
                continue
            for job_id, title, url in parse(page, site.base):
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
    return ("Vacantes nuevas en portales de empresas (postúlate tú: piden cuenta en su sitio):\n"
            + "\n".join(rows) + more)
