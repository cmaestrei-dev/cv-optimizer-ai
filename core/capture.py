"""Captura de una vacante desde su enlace (una página que el usuario pide; no es scraping masivo).

1. Si la página publica schema.org `JobPosting` (LinkedIn público, elempleo, Magneto…), se usa eso.
2. Si no (p. ej. Computrabajo), se toma el texto visible de <main>/<article>/<body>.

Seguridad: solo http(s), y se rechaza cualquier destino —incluidas las redirecciones— que resuelva a
una IP privada, de loopback, link-local o reservada (evita que la app sirva para leer la red interna).
"""

import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

MAX_BYTES = 3_000_000
MAX_REDIRECTS = 3
MAX_TEXT = 15_000
TIMEOUT = (8, 15)
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
_PLATFORMS = {
    "linkedin.com": "LinkedIn",
    "computrabajo.com": "Computrabajo",
    "magneto365.com": "Magneto",
    "elempleo.com": "elempleo",
}


class CaptureError(RuntimeError):
    pass


@dataclass
class CapturedVacancy:
    url: str
    platform: str
    text: str
    source: str  # "jobposting" | "page"
    title: str = ""
    company: str = ""


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return next((name for domain, name in _PLATFORMS.items() if host == domain or host.endswith("." + domain)),
                "Página de la empresa")


def _check_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise CaptureError("El enlace debe empezar por https:// o http://")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise CaptureError("No encontramos ese sitio. Revisa el enlace.") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise CaptureError("Ese enlace apunta a una dirección interna y no está permitido.")


def _download(url: str) -> tuple[str, str]:
    """Descarga validando cada salto de redirección. Devuelve (url_final, html)."""
    for _ in range(MAX_REDIRECTS + 1):
        _check_public(url)
        try:
            response = requests.get(
                url, headers={"User-Agent": _USER_AGENT, "Accept-Language": "es-CO,es;q=0.9"},
                timeout=TIMEOUT, allow_redirects=False, stream=True,
            )
        except requests.RequestException as e:
            raise CaptureError("No pudimos abrir el enlace. Intenta de nuevo o pega el texto de la vacante.") from e
        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "")
            response.close()
            if not location:
                break
            url = urljoin(url, location)
            continue
        if response.status_code != 200:
            response.close()
            raise CaptureError(
                f"El sitio respondió {response.status_code}: quizá pide iniciar sesión. Copia y pega el texto de la vacante."
            )
        body = b""
        for chunk in response.iter_content(65536):
            body += chunk
            if len(body) > MAX_BYTES:
                response.close()
                raise CaptureError("La página es demasiado grande. Copia y pega el texto de la vacante.")
        return url, body.decode(response.encoding or "utf-8", errors="replace")
    raise CaptureError("Demasiadas redirecciones. Copia y pega el texto de la vacante.")


class _TextExtractor(HTMLParser):
    """Texto visible de un fragmento HTML, o de <main>/<article>/<body> si se pide una zona."""

    _SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "button"}
    _BREAK = {"p", "br", "li", "div", "h1", "h2", "h3", "h4", "tr", "section", "ul", "ol"}

    def __init__(self, zone: str | None = None):
        super().__init__(convert_charrefs=True)
        self.zone, self.in_zone, self.skip, self.parts = zone, 0 if zone else 1, 0, []

    def handle_starttag(self, tag, attrs):
        if tag == self.zone:
            self.in_zone += 1
        if tag in self._SKIP:
            self.skip += 1
        if tag in self._BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == self.zone and self.in_zone:
            self.in_zone -= 1
        if tag in self._SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.in_zone and not self.skip and data.strip():
            self.parts.append(data.strip() + " ")

    def text(self) -> str:
        return re.sub(r"\n\s*\n+", "\n", "".join(self.parts)).strip()


def html_to_text(fragment: str, zone: str | None = None) -> str:
    parser = _TextExtractor(zone)
    parser.feed(fragment)
    return parser.text()


def _job_postings(html: str) -> list[dict]:
    found = []
    for match in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        found += [i for i in items if isinstance(i, dict) and "JobPosting" in str(i.get("@type", ""))]
    return found


def _name(value) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "")
    if isinstance(value, list):
        return ", ".join(filter(None, (_name(v) for v in value)))
    return str(value or "")


def _location(value) -> str:
    places = value if isinstance(value, list) else [value]
    parts = []
    for place in places:
        address = place.get("address", {}) if isinstance(place, dict) else {}
        if isinstance(address, dict):
            fields = (address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry"))
            parts.append(", ".join(filter(None, (_name(f) for f in fields))))
    return "; ".join(p for p in parts if p)


def _posting_text(posting: dict) -> str:
    lines = [f"Cargo: {posting.get('title', '')}"]
    for label, value in (
        ("Empresa", _name(posting.get("hiringOrganization"))),
        ("Ubicación", _location(posting.get("jobLocation"))),
        ("Tipo de empleo", _name(posting.get("employmentType"))),
        ("Publicada", str(posting.get("datePosted") or "")[:10]),
        ("Vigente hasta", str(posting.get("validThrough") or "")[:10]),
    ):
        if value:
            lines.append(f"{label}: {value}")
    salary = posting.get("baseSalary")
    if isinstance(salary, dict) and isinstance(salary.get("value"), dict):
        v = salary["value"]
        amount = v.get("value") or "-".join(str(x) for x in (v.get("minValue"), v.get("maxValue")) if x)
        if amount:
            lines.append(f"Salario: {amount} {salary.get('currency', '')} {v.get('unitText', '')}".strip())
    lines.append("")
    lines.append(html_to_text(str(posting.get("description", ""))))
    for label, key in (("Requisitos", "qualifications"), ("Habilidades", "skills"),
                       ("Educación", "educationRequirements"), ("Experiencia", "experienceRequirements")):
        value = posting.get(key)
        text = html_to_text(_name(value) if isinstance(value, dict | list) else str(value or ""))
        if text:
            lines.append(f"{label}: {text}")
    return "\n".join(lines).strip()


def capture_vacancy(url: str) -> CapturedVacancy:
    url = url.strip()
    final_url, html = _download(url)
    platform = detect_platform(final_url)
    postings = _job_postings(html)
    if postings:
        posting = postings[0]
        try:
            return CapturedVacancy(final_url, platform, _posting_text(posting)[:MAX_TEXT], "jobposting",
                                   _name(posting.get("title")), _name(posting.get("hiringOrganization")))
        except (TypeError, ValueError, AttributeError):
            pass  # JobPosting con formato inesperado: se usa el texto visible
    for zone in ("main", "article", "body"):
        text = html_to_text(html, zone)
        if len(text) > 200:
            return CapturedVacancy(final_url, platform, text[:MAX_TEXT], "page")
    raise CaptureError("No encontramos el texto de la vacante en esa página. Copia y pega el texto.")
