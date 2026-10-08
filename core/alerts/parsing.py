"""Lectura de un correo de alerta de empleo reenviado al buzón de la app. Sin red ni base de datos.

Cada cuenta tiene su dirección: <buzón>+<código>@<dominio>. Gmail conserva el "+código" en la cabecera
Delivered-To que agrega al recibir, así se sabe de quién es el correo.

Seguridad:
- Solo cuenta el primer Authentication-Results (el que escribió el servidor que recibió el correo); los
  de más abajo los puede inventar cualquiera. Se exige DKIM válido y alineado con el remitente, de un
  dominio de la lista (los portales, y Google para la confirmación de reenvío).
- Nunca se abre un enlace del correo. Solo se reconocen las vacantes por su forma y se guardan en su
  forma canónica, sin parámetros: los enlaces de los correos traen tokens (p. ej. `otpToken` de LinkedIn
  inicia sesión sin contraseña).
"""

import re
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser
from urllib.parse import urlparse

# Dominio del remitente → portal. Un subdominio cuenta (p. ej. e.linkedin.com).
PORTAL_SENDERS = {
    "linkedin.com": "LinkedIn",
    "computrabajo.com": "Computrabajo",
    "elempleo.com": "elempleo",
    "magneto365.com": "Magneto",
}
GOOGLE = "google.com"
GMAIL_FORWARDING_SENDER = "forwarding-noreply@google.com"
MAX_LINKS_PER_EMAIL = 30

# Vacante por portal: (dominio, patrón de la ruta, URL canónica a partir del host y del patrón)
_JOB_PATTERNS = (
    ("linkedin.com", re.compile(r"^(?:/comm)?/jobs/view/(?:[^/]*-)?(\d{6,})/?$"),
     lambda host, m: f"https://www.linkedin.com/jobs/view/{m.group(1)}"),
    ("computrabajo.com", re.compile(r"^/ofertas-de-trabajo/(oferta-de-trabajo-de-[a-z0-9-]+-[0-9A-Fa-f]{16,})/?$"),
     lambda host, m: f"https://{host}/ofertas-de-trabajo/{m.group(1)}"),  # el país va en el host (co., mx.…)
    ("elempleo.com", re.compile(r"^/co/ofertas-trabajo/([a-z0-9-]+-\d{6,})/?$"),
     lambda host, m: f"https://www.elempleo.com/co/ofertas-trabajo/{m.group(1)}"),
    ("magneto365.com", re.compile(r"^/co/empleos/([a-z0-9-]+-\d{4,})/?$"),
     lambda host, m: f"https://www.magneto365.com/co/empleos/{m.group(1)}"),
)
_HOST = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$")
_FORWARDING_CODE = re.compile(r"\(#(\d{6,12})\)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@dataclass
class JobLink:
    url: str
    title: str = ""  # texto del enlace en el correo (si lo había)


@dataclass
class ParsedAlert:
    kind: str  # "alerta" | "confirmacion" | "rechazado"
    token: str = ""
    portal: str = ""
    sender_domain: str = ""
    sender: str = ""  # dirección del remitente; solo se registra si es de un portal (no es un dato personal)
    links: list[JobLink] = field(default_factory=list)
    forwarding_code: str = ""
    forwarding_from: str = ""
    reason: str = ""  # por qué se rechazó (para el registro; sin datos personales)
    foreign: bool = False  # llegó a la dirección de alertas pero no es de un portal: ¿se reenvía todo el correo?


def _domain(address: str) -> str:
    return parseaddr(address)[1].rpartition("@")[2].lower().strip(".")


def _within(domain: str, allowed: str) -> bool:
    return domain == allowed or domain.endswith("." + allowed)


def _token(msg: EmailMessage, mailbox: str) -> str:
    """El código de la dirección a la que llegó: primero Delivered-To (lo escribe nuestro servidor)."""
    local, _, domain = mailbox.lower().partition("@")
    pattern = re.compile(rf"^{re.escape(local)}\+([a-z0-9]{{8,64}})@{re.escape(domain)}$")
    for header in ("Delivered-To", "X-Forwarded-To", "To"):
        for _, address in getaddresses([str(v) for v in msg.get_all(header, [])]):
            if match := pattern.match(address.lower()):
                return match.group(1)
    return ""


def _without_comments(text: str) -> str:
    """Quita los textos entre comillas y los comentarios (…), que pueden anidarse (RFC 8601). Ahí van
    datos que escribe el remitente (p. ej. su MAIL FROM), así que nunca se leen como resultados."""
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    previous = None
    while previous != text:
        previous, text = text, re.sub(r"\([^()]*\)", " ", text)
    return text


def _auth_results(msg: EmailMessage) -> list[tuple[str, str, dict[str, str]]]:
    """[(método, resultado, propiedades)] del primer Authentication-Results, si lo escribió Google."""
    headers = msg.get_all("Authentication-Results", [])
    if not headers:
        return []
    parts = _without_comments(str(headers[0])).split(";")
    if parts[0].split()[:1] != ["mx.google.com"]:
        return []
    results = []
    for part in parts[1:]:
        tokens = part.split()
        if not tokens or "=" not in tokens[0]:
            continue
        method, _, result = tokens[0].partition("=")
        props: dict[str, str] = {}
        for token in tokens[1:]:
            key, sep, value = token.partition("=")
            if sep:
                props.setdefault(key.lower(), value.lower())
        results.append((method.lower(), result.lower(), props))
    return results


def _authenticated_domains(msg: EmailMessage) -> tuple[set[str], str, str]:
    """(dominios con DKIM válido, resultado DMARC, dominio del From según DMARC)."""
    dkim, dmarc, dmarc_from = set(), "", ""
    for method, result, props in _auth_results(msg):
        if method == "dkim" and result == "pass":
            domain = props.get("header.d") or props.get("header.i", "").rpartition("@")[2]
            if _HOST.match(domain):
                dkim.add(domain)
        elif method == "dmarc" and not dmarc:
            dmarc, dmarc_from = result, props.get("header.from", "")
    return dkim, dmarc, dmarc_from


def _authentic_sender(msg: EmailMessage, allowed: str) -> bool:
    """El From es de `allowed` y lo respalda DKIM válido de ese mismo dominio (o DMARC aprobado)."""
    from_domain = _domain(str(msg.get("From", "")))
    if not _within(from_domain, allowed):
        return False
    dkim, dmarc, dmarc_from = _authenticated_domains(msg)
    if dmarc == "pass" and dmarc_from == from_domain:
        return True
    return any(_within(d, allowed) for d in dkim)


class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.anchors.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None


def job_url(href: str) -> str | None:
    """La URL canónica de una vacante de un portal conocido, o None."""
    try:
        parsed = urlparse(href.strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    for domain, pattern, build in _JOB_PATTERNS:
        if _within(host, domain) and _HOST.match(host) and (match := pattern.match(parsed.path)):
            return build(host, match)
    return None


def _anchors(msg: EmailMessage) -> list[tuple[str, str]]:
    html = msg.get_body(preferencelist=("html",))
    if html is not None:
        parser = _Anchors()
        parser.feed(html.get_content())
        return parser.anchors
    plain = msg.get_body(preferencelist=("plain",))
    text = plain.get_content() if plain is not None else ""
    return [(u, "") for u in re.findall(r"https?://[^\s<>\"']+", text)]


def extract_links(msg: EmailMessage) -> list[JobLink]:
    links: dict[str, JobLink] = {}
    for href, text in _anchors(msg):
        url = job_url(href)
        if url is None:
            continue
        current = links.setdefault(url, JobLink(url))
        if len(text) > len(current.title) and len(text) <= 200:  # la tarjeta suele tener el cargo como texto
            current.title = text
        if len(links) >= MAX_LINKS_PER_EMAIL:
            break
    return list(links.values())


def parse(raw: bytes, mailbox: str) -> ParsedAlert:
    msg = message_from_bytes(raw, policy=policy.default)
    token = _token(msg, mailbox)
    if not token:
        return ParsedAlert("rechazado", reason="sin código de cuenta en la dirección")
    sender_address = parseaddr(str(msg.get("From", "")))[1].lower()
    sender = _domain(sender_address)
    subject = str(msg.get("Subject", ""))
    if _within(sender, GOOGLE) and (code := _FORWARDING_CODE.search(subject)):
        if sender_address != GMAIL_FORWARDING_SENDER or not _authentic_sender(msg, GOOGLE):
            return ParsedAlert("rechazado", token, sender_domain=sender, reason="confirmación sin DKIM de Google")
        requester = next((e for e in _EMAIL.findall(subject.replace(code.group(0), "")) if not _within(_domain(e), GOOGLE)), "")
        return ParsedAlert("confirmacion", token, sender_domain=sender, forwarding_code=code.group(1),
                           forwarding_from=requester.lower())
    portal = next((name for domain, name in PORTAL_SENDERS.items() if _within(sender, domain)), "")
    if not portal:
        return ParsedAlert("rechazado", token, reason="remitente que no es un portal conocido", foreign=True)
    allowed = next(domain for domain in PORTAL_SENDERS if _within(sender, domain))
    if not _authentic_sender(msg, allowed):
        return ParsedAlert("rechazado", token, portal, sender, reason="DKIM o DMARC no válidos")
    if allowed == "linkedin.com" and not sender_address.startswith(("jobalerts", "jobs")):  # p. ej. mensajes privados
        return ParsedAlert("rechazado", token, portal, sender, sender_address, reason="correo de LinkedIn que no es de empleos",
                           foreign=True)
    return ParsedAlert("alerta", token, portal, sender, sender_address, links=extract_links(msg))
