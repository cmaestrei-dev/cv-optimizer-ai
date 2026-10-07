"""Puente con el formato Markdown del modelo anterior.

- parse_*: convierte el contenido guardado por la app vieja en datos estructurados (migración).
- render_*: produce el mismo Markdown que esperan los prompts actuales, hasta que el motor
  nuevo (entrega 2c) los reemplace.
"""

import re
from dataclasses import dataclass, field

from core.profile.models import Education, Experience, Skill

_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_PERIOD_IN_PARENS = re.compile(r"\(([^()]*\d{4}[^()]*)\)\s*$")


@dataclass
class ParsedExperience:
    role: str
    company: str = ""
    period_text: str = ""
    country: str = ""
    modality: str = ""
    achievements: list[str] = field(default_factory=list)


@dataclass
class ParsedEducation:
    title: str
    institution: str = ""
    period_text: str = ""
    description: str = ""


def _split_title(text: str) -> tuple[str, str]:
    """'Cargo - Empresa' -> (cargo, empresa). Se corta en el primer ' - '."""
    left, sep, right = text.partition(" - ")
    return (left.strip(), right.strip()) if sep else (text.strip(), "")


def _clean(text: str) -> str:
    return text.strip().strip("[]").strip()


def parse_experience_markdown(content: str) -> list[ParsedExperience]:
    """'### Cargo - Empresa | Periodo | País | Modalidad' seguido de viñetas (uno o varios bloques)."""
    entries: list[ParsedExperience] = []
    current: ParsedExperience | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            fields = [_clean(f) for f in line.lstrip("#").split("|")]
            role, company = _split_title(fields[0])
            current = ParsedExperience(
                role=role,
                company=company,
                period_text=fields[1] if len(fields) > 1 else "",
                country=fields[2] if len(fields) > 2 else "",
                modality=fields[3] if len(fields) > 3 else "",
            )
            entries.append(current)
        elif current is not None:
            current.achievements.append(_BULLET.sub("", line).strip())
        else:
            # Texto sin encabezado: se conserva como logros de una experiencia sin título.
            current = ParsedExperience(role="(Sin cargo)")
            entries.append(current)
            current.achievements.append(_BULLET.sub("", line).strip())
    return entries


def parse_education_markdown(content: str) -> list[ParsedEducation]:
    """Acepta '### Título - Institución | Periodo' (+ '- descripción') y '- Título - Institución (2022-2027)'."""
    entries: list[ParsedEducation] = []
    current: ParsedEducation | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        starts_entry = line.startswith("#") or current is None or bool(
            _PERIOD_IN_PARENS.search(line) or re.search(r"\|\s*.*\d{4}", line)
        )
        if starts_entry:
            text = _BULLET.sub("", line.lstrip("#")).strip()
            head, _, period = text.partition("|")
            period = period.strip()
            if not period:
                match = _PERIOD_IN_PARENS.search(head)
                if match:
                    period = match.group(1).strip()
                    head = head[: match.start()]
            title, institution = _split_title(head)
            current = ParsedEducation(title=title, institution=institution, period_text=period)
            entries.append(current)
        else:
            desc = _BULLET.sub("", line).strip()
            current.description = f"{current.description} {desc}".strip()
    return entries


def render_experiences_markdown(experiences: list[Experience]) -> str:
    blocks = []
    for exp in experiences:
        header = " | ".join(
            part for part in (
                f"{exp.role} - {exp.company}" if exp.company else exp.role,
                exp.period_text, exp.country, exp.modality,
            ) if part
        )
        bullets = "\n".join(f"- {a.text}" for a in exp.achievements)
        blocks.append(f"### {header}\n{bullets}".strip())
    return "\n\n".join(blocks)


def render_skills_markdown(skills: list[Skill]) -> str:
    return "".join(f"- **{s.name}** -> [{s.category}]\n" for s in skills)


def render_education_markdown(education: list[Education]) -> str:
    lines = []
    for edu in education:
        title = f"{edu.title} - {edu.institution}" if edu.institution else edu.title
        lines.append(f"### {title} | {edu.period_text}" if edu.period_text else f"### {title}")
        if edu.description:
            lines.append(f"- {edu.description}")
    return "\n".join(lines)
