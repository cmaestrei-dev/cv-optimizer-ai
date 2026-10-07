"""Etapa 6 — documento del CV y render.

El CV se arma desde datos estructurados (nunca desde HTML/Markdown de la IA) y todo el texto se
escapa. El ajuste a N páginas se hace midiendo el PDF real y quitando lo menos relevante.
"""

import html
from dataclasses import dataclass, field

from weasyprint import HTML

from config import PDF_PAGE_SIZE
from core.engine.selection import Selection
from core.engine.writing import WrittenCV
from models import UserProfile
from services.docx_generator import generate_docx
from services.pdf_generator import CSS_TEMPLATE, deny_all_url_fetcher, strip_emojis

SECTION_TITLES = {
    "es": ("Perfil Profesional", "Experiencia Laboral", "Educación", "Habilidades"),
    "en": ("Professional Summary", "Work Experience", "Education", "Skills"),
}
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

    @property
    def titles(self) -> tuple[str, str, str, str]:
        return SECTION_TITLES.get(self.language, SECTION_TITLES["es"])

    def visible_experiences(self) -> list[CVExperience]:
        return [e for e in self.experiences if e.included]

    def to_markdown(self) -> str:
        t = self.titles
        parts = [f"## {t[0]}", self.summary, "", f"## {t[1]}"]
        for exp in self.visible_experiences():
            parts.append(f"### {exp.header}")
            parts.extend(f"- {b.text}" for b in exp.included)
            parts.append("")
        if self.education:
            parts += [f"## {t[2]}", *(f"### {line}" for line in self.education), ""]
        if self.skill_groups:
            parts += [f"## {t[3]}", *(f"- **{label}:** {', '.join(items)}" for label, items in self.skill_groups)]
        return "\n".join(parts).strip()


def build_document(selection: Selection, written: WrittenCV, language: str) -> CVDocument:
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
        location = " | ".join(p for p in (exp.country, exp.modality) if p)
        experiences.append(CVExperience(exp.role, exp.company, exp.period_text, location, bullets))

    education = []
    for e in selection.education:
        title = f"{e.title} - {e.institution}" if e.institution else e.title
        education.append(f"{title} | {e.period_text}" if e.period_text else title)

    labels = CATEGORY_LABELS_EN if language == "en" else {}
    skill_groups = [(labels.get(cat, cat), [s.name for s in group]) for cat, group in selection.skill_groups]
    return CVDocument(language, written.summary, experiences, education, skill_groups)


def render_html(doc: CVDocument, contact: UserProfile) -> str:
    esc = lambda text: html.escape(strip_emojis(text))  # noqa: E731
    t = doc.titles
    body = [f"<h2>{esc(t[0])}</h2>", f"<p>{esc(doc.summary)}</p>", f"<h2>{esc(t[1])}</h2>"]
    for exp in doc.visible_experiences():
        body.append(f"<h3>{esc(exp.header)}</h3><ul>")
        body.extend(f"<li>{esc(b.text)}</li>" for b in exp.included)
        body.append("</ul>")
    if doc.education:
        body.append(f"<h2>{esc(t[2])}</h2>")
        body.extend(f"<h3>{esc(line)}</h3>" for line in doc.education)
    if doc.skill_groups:
        body.append(f"<h2>{esc(t[3])}</h2><ul>")
        body.extend(f"<li><strong>{esc(label)}:</strong> {esc(', '.join(items))}</li>" for label, items in doc.skill_groups)
        body.append("</ul>")
    name = esc(contact.full_name.upper()) if contact.full_name else ""
    css = CSS_TEMPLATE.replace("{page_size}", PDF_PAGE_SIZE)
    return (
        f'<!DOCTYPE html><html lang="{doc.language}"><head><meta charset="utf-8"><style>{css}</style></head>'
        f'<body><h1>{name}</h1><div class="contacto">{strip_emojis(contact.contact_line_html)}</div>'
        f"{''.join(body)}</body></html>"
    )


def _trim_once(doc: CVDocument) -> str | None:
    """Quita lo menos relevante. Devuelve qué se quitó, o None si ya no hay nada razonable que quitar."""
    candidates = [(b, exp) for exp in doc.visible_experiences() if len(exp.included) > 1 for b in exp.included]
    if candidates:
        bullet, exp = min(candidates, key=lambda pair: pair[0].score)
        bullet.included = False
        return f"Viñeta de {exp.role}: {bullet.text[:60]}…"
    if len(doc.education) > 2:
        return f"Educación: {doc.education.pop()}"
    total_skills = sum(len(items) for _, items in doc.skill_groups)
    if total_skills > 8:
        label, items = doc.skill_groups[-1]
        removed = items.pop()
        if not items:
            doc.skill_groups.pop()
        return f"Habilidad: {removed} ({label})"
    visible = doc.visible_experiences()
    if len(visible) > 1:
        oldest = visible[-1]
        for b in oldest.bullets:
            b.included = False
        return f"Experiencia: {oldest.role}"
    return None


@dataclass
class RenderResult:
    pdf: bytes
    docx: bytes
    pages: int
    trimmed: list[str]


def render(doc: CVDocument, contact: UserProfile, max_pages: int = 1) -> RenderResult:
    trimmed: list[str] = []
    for _ in range(60):
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
