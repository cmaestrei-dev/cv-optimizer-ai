import logging
import re

from models import UserProfile

logger = logging.getLogger(__name__)

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001FAFF"  # emoticons, symbols, pictographs
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed characters
    "\u2600-\u27BF"  # misc symbols
    "\u200D\ufe0f"  # zero-width joiner + variation selector
    "]+",
    flags=re.UNICODE,
)


def strip_emojis(text: str) -> str:
    return _EMOJI_PATTERN.sub("", text)

# Se rellena con .replace("{page_size}", ...), NO con .format: llaves simples.
# Diseño pensado para ATS y para leerse en 6 segundos: una sola columna, texto real (nada de versalitas ni
# imágenes), una sola familia sans incrustada (Liberation Sans = métricas de Arial), 10 pt, sin justificar,
# cargo a la izquierda y fechas a la derecha en la misma línea.
CSS_TEMPLATE = """
@page {
    size: {page_size};
    margin: 0.55in 0.6in 0.5in 0.6in;
}

body {
    font-family: 'Liberation Sans', Arial, Helvetica, sans-serif;
    font-size: 10pt;
    color: #1a1a1a;
    line-height: 1.32;
    margin: 0;
    padding: 0;
}

h1 {
    text-align: center;
    font-size: 21pt;
    font-weight: 700;
    letter-spacing: 0.3pt;
    color: #111111;
    margin: 0;
    padding: 0;
    line-height: 1.1;
}

.titular {
    text-align: center;
    font-size: 10.5pt;
    color: #333333;
    margin: 3pt 0 0 0;
}

.contacto {
    text-align: center;
    font-size: 9pt;
    color: #444444;
    margin: 4pt 0 10pt 0;
}

.contacto a {
    color: #444444;
    text-decoration: none;
    white-space: nowrap;
}

h2 {
    font-size: 10.5pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6pt;
    color: #111111;
    border-bottom: 0.8pt solid #222222;
    margin: 10pt 0 4pt 0;
    padding: 0 0 1.5pt 0;
}

.entrada {
    margin: 6pt 0 0 0;
    break-inside: avoid;
}

.fila {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12pt;
}

.cargo {
    font-weight: 700;
    font-size: 10.5pt;
    color: #111111;
}

.fecha {
    white-space: nowrap;
    font-size: 9.5pt;
    color: #333333;
}

.lugar {
    font-style: italic;
    font-size: 9.5pt;
    color: #333333;
}

p {
    margin: 0 0 2pt 0;
    color: #1a1a1a;
    orphans: 2;
    widows: 2;
}

ul {
    margin: 2pt 0 0 0;
    padding-left: 13pt;
    list-style-type: disc;
}

ul li {
    margin-bottom: 1.5pt;
    padding-left: 1pt;
}

ul li::marker {
    color: #333333;
}

.habilidades p {
    margin: 0 0 2pt 0;
}

strong {
    color: #111111;
}
"""


def clean_markdown_output(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```markdown"):
        text = text[11:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _sanitize_filename_part(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s\-_]", "", text)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned[:40]


def build_pdf_filename(profile: UserProfile, role: str = "", company: str = "") -> str:
    parts = []
    if profile.full_name:
        parts.append(_sanitize_filename_part(profile.full_name))
    if role and role.lower() not in ("no especificada", "no especificado"):
        parts.append(_sanitize_filename_part(role))
    if company and company.lower() not in ("no especificada", "no especificado"):
        parts.append(_sanitize_filename_part(company))
    if not parts:
        return "cv_adaptado.pdf"
    return "_".join(parts) + ".pdf"


def deny_all_url_fetcher(url: str, *args, **kwargs):
    # El CV no necesita recursos externos. Sin esto, HTML inyectado (perfil o salida del LLM)
    # podría incrustar archivos del servidor (file://) o hacer peticiones internas (SSRF).
    raise ValueError(f"Recurso externo bloqueado: {url}")
