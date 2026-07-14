import logging
import re

import markdown
from weasyprint import HTML

from config import PDF_PAGE_SIZE
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


def _strip_emojis(text: str) -> str:
    return _EMOJI_PATTERN.sub("", text)

CSS_TEMPLATE = """
@page {{
    size: {page_size};
    margin: 0.5in 0.5in 0.5in 0.5in;
    @bottom-center {{
        content: none;
    }}
}}

body {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 8pt;
    color: #1e1e1e;
    line-height: 1.25;
    margin: 0;
    padding: 0;
}}

h1 {{
    font-family: Georgia, 'Times New Roman', serif;
    text-align: center;
    font-size: 17pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 3pt;
    color: #111111;
    margin: 0 0 2pt 0;
    padding: 0;
}}

.contacto {{
    text-align: center;
    font-size: 7pt;
    color: #555555;
    margin: 0 0 12pt 0;
    letter-spacing: 0.2pt;
}}

.contacto a {{
    color: #555555;
    text-decoration: none;
}}

h2 {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 7.5pt;
    font-weight: 700;
    font-variant: small-caps;
    letter-spacing: 1.8pt;
    text-transform: lowercase;
    color: #2a2a2a;
    border-bottom: 0.4pt solid #444444;
    margin: 12pt 0 4pt 0;
    padding: 0 0 2pt 0;
}}

h3 {{
    font-size: 8pt;
    font-weight: 600;
    margin: 7pt 0 1pt 0;
    color: #1e1e1e;
    padding: 0;
}}

p {{
    font-size: 8pt;
    margin: 0 0 2pt 0;
    text-align: justify;
    color: #2a2a2a;
    orphans: 2;
    widows: 2;
}}

ul {{
    margin: 1pt 0 3pt 0;
    padding-left: 12pt;
    list-style-type: none;
}}

ul li {{
    font-size: 8pt;
    margin-bottom: 1pt;
    color: #2a2a2a;
    text-align: justify;
    position: relative;
    padding-left: 0;
}}

ul li::before {{
    content: "–";
    position: absolute;
    left: -10pt;
    color: #666666;
    font-size: 7pt;
}}

strong {{
    color: #111111;
}}
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


def parse_vacancy_fields(vacancy_text: str) -> tuple[str, str]:
    role = ""
    company = ""
    for line in vacancy_text.split("\n"):
        if line.upper().startswith("ROLE:"):
            role = line.split(":", 1)[1].strip()
        elif line.upper().startswith("COMPANY:"):
            company = line.split(":", 1)[1].strip()
    return role, company


def build_html(cv_markdown: str, profile: UserProfile) -> str:
    cleaned = clean_markdown_output(cv_markdown)
    cleaned = _strip_emojis(cleaned)
    content_html = markdown.markdown(cleaned, tab_length=2)

    full_name = _strip_emojis(profile.full_name.upper()) if profile.full_name else ""

    css_filled = CSS_TEMPLATE.replace("{page_size}", PDF_PAGE_SIZE)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
{css_filled}
</style>
</head>
<body>
<h1>{full_name}</h1>
<div class="contacto">
{_strip_emojis(profile.contact_line_html)}
</div>
{content_html}
</body>
</html>"""


def generate_pdf(
    cv_markdown: str,
    profile: UserProfile,
) -> bytes:
    html_content = build_html(cv_markdown, profile)

    doc = HTML(string=html_content)
    return doc.write_pdf(target=None)
