"""Etapa 4 — redacción controlada.

La IA solo reescribe viñetas y el resumen. Cargos, empresas, fechas, educación y habilidades salen
de los datos del usuario, así que no los puede inventar. Cada texto pasa por verification.py; lo
que no se respalda se corrige una vez y, si sigue fallando, se usa el texto original.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from core.engine.matching import MatchResult
from core.engine.selection import Selection
from core.engine.verification import unsupported
from core.llm.client import LLMClient
from core.llm.structured import generate_structured
from core.profile.snapshot import ProfileSnapshot
from core.vacancy import VacancyAnalysis

LANGUAGE_NAMES = {"es": "español", "en": "inglés", "pt": "portugués", "fr": "francés"}
SOURCE_LANGUAGE = "es"  # los perfiles se registran en español


class WrittenBullet(BaseModel):
    id: int
    text: str = Field(description="Viñeta reescrita, una oración")


class Draft(BaseModel):
    summary: str = Field(default="", description="Perfil profesional de 3 a 4 líneas")
    bullets: list[WrittenBullet] = Field(default_factory=list)


@dataclass
class WrittenCV:
    summary: str
    bullets: dict[int, str]
    reverted: dict[int, list[str]] = field(default_factory=dict)  # id -> motivos
    summary_problems: list[str] = field(default_factory=list)


_PROMPT = """Eres un redactor experto de CVs para cualquier profesión. Reescribe el contenido del \
candidato para esta vacante SIN INVENTAR NADA.

VACANTE: {role}{company} | Área: {area}
Palabras clave de la vacante: {keywords}
IDIOMA DEL CV: {language}
Enfoque pedido por el candidato: {focus}

LOGROS A REESCRIBIR (id | experiencia | requisitos de la vacante que respalda | texto original):
{bullets}

DATOS PARA EL RESUMEN:
- Años totales de experiencia (calculados): {years}
- Cargos reales: {roles}
- Habilidades reales: {skills}

REGLAS:
1. Cada viñeta usa SOLO hechos de su texto original. Puedes reordenar, acortar, traducir y nombrar \
lo mismo con el término que usa la vacante (sinónimo exacto), nada más.
2. PROHIBIDO agregar herramientas, software, empresas, cifras, porcentajes, resultados o \
responsabilidades que no estén en el texto original. Conserva las cifras tal cual.
3. Cada viñeta: una oración de máximo 200 caracteres que empieza con un verbo de acción en \
pasado (primera persona en español). No termines con punto.
4. Devuelve una viñeta por cada id recibido, con el mismo id.
5. Resumen: 3-4 líneas en primera persona implícita, empieza con el cargo exacto de la vacante \
("{role}"), menciona solo años, cargos y habilidades de los DATOS PARA EL RESUMEN y de los logros.
6. Todo en {language}."""

_REPAIR = """Estas viñetas reescritas contienen datos que NO están en su texto original. \
Reescríbelas de nuevo usando SOLO el texto original (idioma: {language}). Mismo formato y reglas.

{items}"""


def _years_text(match: MatchResult) -> str:
    years = int(match.experience_years)
    return f"{years}" if years >= 1 else "menos de 1"


def write_cv(
    llm: LLMClient,
    vacancy: VacancyAnalysis,
    selection: Selection,
    match: MatchResult,
    profile: ProfileSnapshot,
    *,
    extra_focus: str = "",
) -> WrittenCV:
    language_code = (vacancy.language or SOURCE_LANGUAGE).lower()[:2]
    language = LANGUAGE_NAMES.get(language_code, vacancy.language or "español")
    requirement_texts = {i: m.requirement.text for i, m in enumerate(match.requirements, start=1)}

    originals: dict[int, str] = {}
    lines = []
    for sel in selection.experiences:
        header = f"{sel.experience.role} @ {sel.experience.company}" if sel.experience.company else sel.experience.role
        for a in sel.achievements:
            originals[a.id] = a.text
            reqs = "; ".join(
                requirement_texts[i] for i in sorted(match.achievement_requirements.get(a.id, ())) if i in requirement_texts
            ) or "-"
            lines.append(f"{a.id} | {header} | {reqs} | {a.text}")

    skills = [s.name for _, group in selection.skill_groups for s in group]
    prompt = _PROMPT.format(
        role=vacancy.role,
        company=f" en {vacancy.company}" if vacancy.company else "",
        area=vacancy.area or "-",
        keywords=", ".join(vacancy.keywords) or "-",
        language=language,
        focus=extra_focus.strip() or "ninguno",
        bullets="\n".join(lines),
        years=_years_text(match),
        roles=", ".join(dict.fromkeys(e.role for e in profile.experiences)) or "-",
        skills=", ".join(skills) or "-",
    )
    draft = generate_structured(llm, prompt, Draft, cache=False)

    strict = language_code == SOURCE_LANGUAGE
    written = {b.id: b.text.strip().rstrip(".") for b in draft.bullets if b.id in originals}
    problems = {
        aid: unsupported(written[aid], originals[aid], strict=strict) if aid in written else ["sin respuesta"]
        for aid in originals
    }
    failing = {aid: p for aid, p in problems.items() if p}

    if failing:
        items = "\n".join(
            f"{aid} | original: {originals[aid]} | tu versión: {written.get(aid, '-')} | problemas: {'; '.join(p)}"
            for aid, p in failing.items()
        )
        repaired = generate_structured(llm, _REPAIR.format(language=language, items=items), Draft, cache=False)
        for b in repaired.bullets:
            if b.id in failing:
                text = b.text.strip().rstrip(".")
                if not unsupported(text, originals[b.id], strict=strict):
                    written[b.id] = text
                    failing.pop(b.id)

    for aid in failing:
        written[aid] = originals[aid].rstrip(".")  # el texto del usuario nunca miente

    summary_source = " ".join(
        [
            *originals.values(), *skills, vacancy.role, vacancy.area,
            *(f"{e.role} {e.company}" for e in profile.experiences),
            *(f"{e.title} {e.institution}" for e in profile.education),
        ]
    )
    summary_problems = unsupported(
        draft.summary, summary_source, strict=strict,
        extra_numbers={str(int(match.experience_years)), str(round(match.experience_years))},
    )
    return WrittenCV(
        summary=fallback_summary(vacancy, match, profile, language_code) if summary_problems or not draft.summary.strip()
        else draft.summary.strip(),
        bullets=written,
        reverted=failing,
        summary_problems=summary_problems,
    )


def fallback_summary(vacancy: VacancyAnalysis, match: MatchResult, profile: ProfileSnapshot, language_code: str) -> str:
    """Resumen armado solo con datos reales, para cuando el de la IA no pasa la verificación."""
    roles = list(dict.fromkeys(e.role for e in profile.experiences))[:3]
    years = _years_text(match)
    if language_code == "en":
        return f"{vacancy.role} candidate with {years} years of experience as {', '.join(roles)}."
    return f"{vacancy.role}: {years} años de experiencia como {', '.join(roles)}."
