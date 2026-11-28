"""Etapa 6 — documento del CV y render.

El CV se arma desde datos estructurados (nunca desde HTML/Markdown de la IA) y todo el texto se
escapa. El ajuste a N páginas se hace midiendo el PDF real y quitando lo menos relevante.
"""

import html
from dataclasses import asdict, dataclass, field

from weasyprint import HTML

from config import PDF_PAGE_SIZE
from core.engine import skill_groups as tech
from core.engine.selection import Selection, is_degree_title
from core.engine.writing import WrittenCV
from models import UserProfile
from services.docx_generator import generate_docx
from services.pdf_generator import CSS_TEMPLATE, deny_all_url_fetcher, strip_emojis

SECTION_TITLES = {
    "es": ("Perfil Profesional", "Experiencia Laboral", "Educación", "Habilidades"),
    "en": ("Professional Summary", "Work Experience", "Education", "Skills"),
}
KEY_SKILLS_LABEL = {"es": "Competencias clave", "en": "Key skills"}
# Último recurso antes de quitar viñetas por debajo de 4: letra un poco más pequeña y luego márgenes más estrechos.
DENSITY_CSS = (
    "",
    "body { font-size: 9.5pt; line-height: 1.28; } .cargo { font-size: 10pt; } h2 { margin: 8pt 0 3pt 0; }"
    " .entrada { margin-top: 4pt; }",
    "body { font-size: 9.5pt; line-height: 1.25; } .cargo { font-size: 10pt; } h2 { margin: 7pt 0 3pt 0; }"
    " .entrada { margin-top: 3pt; } @page { margin: 0.45in 0.5in 0.4in 0.5in; }",
)
CATEGORY_LABELS_EN = {
    "Herramientas y software": "Tools & software",
    "Conocimientos del área": "Domain knowledge",
    "Procesos y metodologías": "Processes & methodologies",
    "Idiomas": "Languages",
    "Habilidades blandas": "Soft skills",
    "Otros": "Other",
    "Lenguajes de Programación": "Programming languages",
    "Frameworks / Librerías": "Frameworks & libraries",
    "Bases de Datos": "Databases",
    "Herramientas / DevOps": "Tools & DevOps",
    "Metodologías / Soft Skills": "Methodologies & soft skills",
    **tech.LABELS_EN,
}


@dataclass
class CVBullet:
    achievement_id: int
    text: str
    original: str
    score: float
    reverted: bool = False
    included: bool = True


@dataclass
class CVExperience:
    role: str
    company: str
    period_text: str
    location: str
    bullets: list[CVBullet] = field(default_factory=list)

    @property
    def header(self) -> str:
        title = f"{self.role} - {self.company}" if self.company else self.role
        return " | ".join(p for p in (title, self.period_text, self.location) if p)

    @property
    def included(self) -> list[CVBullet]:
        return [b for b in self.bullets if b.included and b.text.strip()]


@dataclass
class CVDocument:
    language: str
    summary: str
    experiences: list[CVExperience]
    education: list[str]
    skill_groups: list[tuple[str, list[str]]]
    key_skills: list[str] = field(default_factory=list)  # palabras de la vacante que el perfil respalda (keywords.py)
    density: int = 0  # índice de DENSITY_CSS

    @property
    def titles(self) -> tuple[str, str, str, str]:
        return SECTION_TITLES.get(self.language, SECTION_TITLES["es"])

    @property
    def key_skills_label(self) -> str:
        return KEY_SKILLS_LABEL.get(self.language, KEY_SKILLS_LABEL["es"])

    def visible_experiences(self) -> list[CVExperience]:
        return [e for e in self.experiences if e.included]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CVDocument":
        return cls(
            language=data["language"],
            summary=data["summary"],
            experiences=[
                CVExperience(**{**e, "bullets": [CVBullet(**b) for b in e["bullets"]]}) for e in data["experiences"]
            ],
            education=list(data["education"]),
            skill_groups=[(label, list(items)) for label, items in data["skill_groups"]],
            key_skills=list(data.get("key_skills") or []),  # los CV guardados antes de la v3 no la traen
            density=int(data.get("density") or 0),
        )

    def to_markdown(self) -> str:
        t = self.titles
        parts = [f"## {t[0]}", self.summary]
        if self.key_skills:
            parts.append(f"**{self.key_skills_label}:** {' · '.join(self.key_skills)}")
        parts += ["", f"## {t[1]}"]
        for exp in self.visible_experiences():
            parts.append(f"### {exp.header}")
            parts.extend(f"- {b.text}" for b in exp.included)
            parts.append("")
        if self.education:
            parts += [f"## {t[2]}", *(f"### {line}" for line in self.education), ""]
        if self.skill_groups:
            parts += [f"## {t[3]}", *(f"- **{label}:** {', '.join(items)}" for label, items in self.skill_groups)]
        return "\n".join(parts).strip()


def build_document(selection: Selection, written: WrittenCV, language: str, key_skills: list[str] | None = None) -> CVDocument:
    language = language if language in SECTION_TITLES else "es"
    experiences = []
    for sel in selection.experiences:
        exp = sel.experience
        bullets = [
            CVBullet(
                achievement_id=a.id,
                text=written.bullets.get(a.id, a.text),
                original=a.text,
                score=selection.scores.get(a.id, 0.0),
                reverted=a.id in written.reverted,
            )
            for a in sel.achievements
        ]
        location = " · ".join(p for p in (exp.country, exp.modality) if p)
        experiences.append(CVExperience(exp.role, exp.company, exp.period_text, location, bullets))

    education = []
    for e in selection.education:
        title = f"{e.title} - {e.institution}" if e.institution else e.title
        education.append(f"{title} | {e.period_text}" if e.period_text else title)

    labels = CATEGORY_LABELS_EN if language == "en" else {}
    skill_groups = [(labels.get(cat, cat), [s.name for s in group]) for cat, group in selection.skill_groups]
    return CVDocument(language, written.summary, experiences, education, skill_groups, list(key_skills or []))


def _entry(left: str, right: str, below: str = "") -> str:
    """Una entrada: lo principal a la izquierda y la fecha a la derecha (mismo orden en el texto del PDF)."""
    row = f'<div class="fila"><span class="cargo">{left}</span>' + (f'<span class="fecha">{right}</span>' if right else "") + "</div>"
    return row + (f'<div class="lugar">{below}</div>' if below else "")


def render_html(doc: CVDocument, contact: UserProfile) -> str:
    esc = lambda text: html.escape(strip_emojis(text))  # noqa: E731
    t = doc.titles
    body = []
    if doc.summary.strip() or doc.key_skills:
        body.append(f"<h2>{esc(t[0])}</h2>")
    if doc.summary.strip():
        body.append(f"<p>{esc(doc.summary)}</p>")
    if doc.key_skills:  # texto visible y normal: lo que lee el ATS es lo mismo que ve el reclutador
        body.append(f'<p class="clave"><strong>{esc(doc.key_skills_label)}:</strong> {esc(" · ".join(doc.key_skills))}</p>')
    body.append(f"<h2>{esc(t[1])}</h2>")
    for exp in doc.visible_experiences():
        below = " · ".join(esc(p) for p in (exp.company, exp.location) if p)
        body.append(f'<div class="entrada">{_entry(esc(exp.role), esc(exp.period_text), below)}<ul>')
        body.extend(f"<li>{esc(b.text)}</li>" for b in exp.included)
        body.append("</ul></div>")
    if doc.education:
        body.append(f"<h2>{esc(t[2])}</h2>")
        for line in doc.education:  # "Título - Institución | Periodo" (ver build_document)
            text, sep, period = line.rpartition(" | ")
            text, period = (text, period) if sep else (line, "")
            title, sep, institution = text.rpartition(" - ")
            title, institution = (title, institution) if sep else (text, "")
            body.append(f'<div class="entrada">{_entry(esc(title), esc(period), esc(institution))}</div>')
    if doc.skill_groups:
        body.append(f'<h2>{esc(t[3])}</h2><div class="habilidades">')
        body.extend(f"<p><strong>{esc(label)}:</strong> {esc(', '.join(items))}</p>" for label, items in doc.skill_groups)
        body.append("</div>")
    name = esc(contact.full_name) if contact.full_name else ""
    headline = f'<div class="titular">{esc(contact.headline)}</div>' if contact.headline.strip() else ""
    css = CSS_TEMPLATE.replace("{page_size}", PDF_PAGE_SIZE) + DENSITY_CSS[min(max(doc.density, 0), len(DENSITY_CSS) - 1)]
    return (
        f'<!DOCTYPE html><html lang="{doc.language}"><head><meta charset="utf-8"><style>{css}</style></head>'
        f'<body><h1>{name}</h1>{headline}<div class="contacto">{strip_emojis(contact.contact_line_html)}</div>'
        f"{''.join(body)}</body></html>"
    )


def _drop_bullet(doc: CVDocument, keep: int) -> str | None:
    """La viñeta de menor puntaje entre las experiencias que tienen más de `keep`."""
    candidates = [(b, exp) for exp in doc.visible_experiences() if len(exp.included) > keep for b in exp.included]
    if not candidates:
        return None
    bullet, exp = min(candidates, key=lambda pair: pair[0].score)
    bullet.included = False
    return f"Viñeta de {exp.role}: {bullet.text[:60]}…"


def _drop_course(doc: CVDocument, keep: int) -> str | None:
    """El último curso o certificado (van del más al menos relevante, después de los títulos)."""
    courses = [i for i, line in enumerate(doc.education) if not is_degree_title(line.split(" - ")[0])]
    if len(courses) <= keep:
        return None
    return f"Educación: {doc.education.pop(courses[-1])}"


def _drop_education(doc: CVDocument, keep: int) -> str | None:
    return f"Educación: {doc.education.pop()}" if len(doc.education) > keep else None


def _drop_skill(doc: CVDocument, keep: int) -> str | None:
    """La última habilidad del último grupo (los grupos van de lo que pide la vacante a lo demás)."""
    if sum(len(items) for _, items in doc.skill_groups) <= keep:
        return None
    label, items = doc.skill_groups[-1]
    removed = items.pop()
    if not items:
        doc.skill_groups.pop()
    return f"Habilidad: {removed} ({label})"


def _denser(doc: CVDocument) -> str | None:
    if doc.density >= len(DENSITY_CSS) - 1:
        return None
    doc.density += 1
    return "Letra un poco más pequeña" if doc.density == 1 else "Márgenes más estrechos"


def _drop_oldest(doc: CVDocument) -> str | None:
    visible = doc.visible_experiences()
    if len(visible) <= 1:
        return None
    for b in visible[-1].bullets:
        b.included = False
    return f"Experiencia: {visible[-1].role}"


def _trim_once(doc: CVDocument) -> str | None:
    """Quita lo menos relevante. Devuelve qué se quitó, o None si ya no hay nada razonable que quitar.

    Orden (v3, 2026-11-28: cada experiencia lleva 4 o 5 viñetas y la hoja es una sola): viñetas por encima de 5, cursos
    hasta dejar los 2 más relevantes, habilidades hasta 12, la 5.ª viñeta, letra y márgenes más compactos, el resto de
    los cursos y recién entonces viñetas por debajo de 4. Los títulos y la experiencia más antigua van al final.
    """
    steps = (
        lambda: _drop_bullet(doc, 5), lambda: _drop_course(doc, 2), lambda: _drop_skill(doc, 12),
        lambda: _drop_bullet(doc, 4), lambda: _denser(doc), lambda: _drop_course(doc, 0),
        lambda: _drop_bullet(doc, 3), lambda: _drop_education(doc, 2), lambda: _drop_skill(doc, 8),
        lambda: _drop_oldest(doc), lambda: _drop_bullet(doc, 2), lambda: _drop_bullet(doc, 1),
    )
    for step in steps:
        if removed := step():
            return removed
    return None


@dataclass
class RenderResult:
    pdf: bytes
    docx: bytes
    pages: int
    trimmed: list[str]


def render(doc: CVDocument, contact: UserProfile, max_pages: int = 1) -> RenderResult:
    trimmed: list[str] = []
    for _ in range(80):
        rendered = HTML(string=render_html(doc, contact), url_fetcher=deny_all_url_fetcher).render()
        if len(rendered.pages) <= max_pages:
            break
        removed = _trim_once(doc)
        if removed is None:
            break
        trimmed.append(removed)
    return RenderResult(
        pdf=rendered.write_pdf(),
        docx=generate_docx(doc.to_markdown(), contact),
        pages=len(rendered.pages),
        trimmed=trimmed,
    )
