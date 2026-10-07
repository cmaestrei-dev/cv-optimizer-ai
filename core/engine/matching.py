"""Etapa 2 — match requisito ↔ evidencia.

La IA solo propone qué evidencia del perfil respalda cada requisito; el código valida que esa
evidencia exista, corrige los requisitos de años con las fechas reales y calcula el puntaje.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from core.llm.client import LLMClient
from core.llm.structured import generate_structured
from core.profile.snapshot import ProfileSnapshot
from core.vacancy import Requirement, VacancyAnalysis

Level = Literal["cubre", "parcial", "no"]
LEVEL_VALUE = {"cubre": 1.0, "parcial": 0.5, "no": 0.0}
KIND_WEIGHT = {"obligatorio": 1.0, "deseable": 0.4}
FUNCTION_WEIGHT = 0.3  # parecerse a las funciones del cargo suma relevancia, no puntaje
FUNCTION_OFFSET = 1000  # ids de funciones en achievement_requirements (para la diversidad)
_YEARS = re.compile(r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:años|anos|year|years|yrs)", re.IGNORECASE)


class RequirementEvidence(BaseModel):
    requirement: int = Field(description="Número del requisito (R#)")
    level: Level = Field(
        description="'cubre' si la evidencia lo demuestra; 'parcial' si es relacionada pero "
        "incompleta (menos nivel, menos años, herramienta similar); 'no' si no hay evidencia"
    )
    evidence: list[str] = Field(
        default_factory=list, description="Referencias del perfil que lo respaldan: L#, H#, E#"
    )
    note: str = Field(default="", description="Explicación breve (máx. 15 palabras)")


class FunctionEvidence(BaseModel):
    function: int = Field(description="Número de la función (F#)")
    evidence: list[str] = Field(default_factory=list, description="Logros (L#) que muestran haberla hecho")


class EvidenceMap(BaseModel):
    items: list[RequirementEvidence] = Field(default_factory=list)
    functions: list[FunctionEvidence] = Field(default_factory=list)


@dataclass
class RequirementMatch:
    requirement: Requirement
    level: Level
    evidence: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def weight(self) -> float:
        return KIND_WEIGHT[self.requirement.kind]


@dataclass
class MatchResult:
    score: int
    requirements: list[RequirementMatch]
    experience_years: float
    required_years: float | None
    achievement_weights: dict[int, float]
    achievement_requirements: dict[int, set[int]]
    cited_skills: set[int]
    cited_education: set[int]

    @property
    def must_haves(self) -> list[RequirementMatch]:
        return [m for m in self.requirements if m.requirement.kind == "obligatorio"]

    @property
    def gaps(self) -> list[RequirementMatch]:
        return [m for m in self.requirements if m.level != "cubre"]

    @property
    def meets_years(self) -> bool | None:
        return None if self.required_years is None else self.experience_years >= self.required_years


def profile_catalog(profile: ProfileSnapshot) -> tuple[str, set[str]]:
    """Texto con referencias (L# logros, H# habilidades, E# educación) y el conjunto de refs válidas."""
    lines, refs = [], set()
    for exp in profile.experiences:
        header = f"{exp.role} @ {exp.company}" if exp.company else exp.role
        if exp.period_text:
            header += f" ({exp.period_text})"
        for a in exp.achievements:
            lines.append(f"L{a.id}: [{header}] {a.text}")
            refs.add(f"L{a.id}")
    for s in profile.skills:
        lines.append(f"H{s.id}: {s.name} ({s.category})")
        refs.add(f"H{s.id}")
    for e in profile.education:
        title = f"{e.title} - {e.institution}" if e.institution else e.title
        lines.append(f"E{e.id}: {title}{f' ({e.period_text})' if e.period_text else ''}")
        refs.add(f"E{e.id}")
    return "\n".join(lines), refs


_PROMPT = """Eres un evaluador de candidatos para un sistema ATS. Para cada requisito de la vacante, \
indica qué elementos del perfil del candidato lo respaldan.

REQUISITOS DE LA VACANTE (R#):
{requirements}

FUNCIONES DEL CARGO (F#):
{functions}

PERFIL DEL CANDIDATO (L# = logro, H# = habilidad, E# = educación):
{catalog}

Años totales de experiencia del candidato (calculados con sus fechas): {years}

Reglas:
1. Cita SOLO referencias que existan en el perfil y que realmente demuestren el requisito.
2. Acepta sinónimos y equivalencias reales del oficio (p. ej. "manejo de cartera" ≈ "cuentas por cobrar"), \
pero NUNCA supongas habilidades que el perfil no menciona.
3. 'parcial' cuando la evidencia es relacionada pero no alcanza (menos años, nivel menor, herramienta similar).
4. Devuelve un elemento por cada requisito, en orden, en "items".
5. En "functions", para cada función indica los logros (L#) que muestran que el candidato ya hizo algo equivalente (lista vacía si ninguno)."""


def build_evidence_map(llm: LLMClient, vacancy: VacancyAnalysis, profile: ProfileSnapshot) -> EvidenceMap:
    catalog, _ = profile_catalog(profile)
    requirements = "\n".join(
        f"R{i}: {r.text} [{r.kind}, {r.category}]" for i, r in enumerate(vacancy.requirements, start=1)
    )
    years = round(profile.total_experience_months() / 12, 1)
    functions = "\n".join(f"F{i}: {f}" for i, f in enumerate(vacancy.responsibilities, start=1))
    prompt = _PROMPT.format(
        requirements=requirements or "(sin requisitos)", functions=functions or "(sin funciones)",
        catalog=catalog or "(vacío)", years=years,
    )
    return generate_structured(llm, prompt, EvidenceMap)


def _norm(ref: str) -> str:
    return ref.strip().upper()


def _required_years(text: str) -> float | None:
    match = _YEARS.search(text)
    return float(match.group(1).replace(",", ".")) if match else None


def compute_match(
    vacancy: VacancyAnalysis,
    evidence_map: EvidenceMap,
    profile: ProfileSnapshot,
    today: date | None = None,
) -> MatchResult:
    _, valid_refs = profile_catalog(profile)
    experience_years = round(profile.total_experience_months(today) / 12, 1)
    by_index = {item.requirement: item for item in evidence_map.items}

    matches: list[RequirementMatch] = []
    for i, requirement in enumerate(vacancy.requirements, start=1):
        item = by_index.get(i)
        evidence = [ref for ref in (_norm(r) for r in (item.evidence if item else [])) if ref in valid_refs]
        level: Level = item.level if item and evidence else "no"
        note = item.note if item else ""
        # Los años se verifican con las fechas reales, no con la opinión de la IA.
        needed = _required_years(requirement.text) if requirement.category == "experiencia" else None
        if needed is not None and experience_years < needed and level == "cubre":
            level = "parcial"
            note = f"Tienes {experience_years:g} de {needed:g} años requeridos"
        matches.append(RequirementMatch(requirement, level, evidence, note))

    total_weight = sum(m.weight for m in matches)
    score = round(100 * sum(m.weight * LEVEL_VALUE[m.level] for m in matches) / total_weight) if total_weight else 0

    achievement_weights: dict[int, float] = {}
    achievement_requirements: dict[int, set[int]] = {}
    cited_skills: set[int] = set()
    cited_education: set[int] = set()
    for index, m in enumerate(matches, start=1):
        value = m.weight * LEVEL_VALUE[m.level]
        for ref in m.evidence:
            kind, ref_id = ref[0], int(ref[1:])
            if kind == "L":
                achievement_weights[ref_id] = achievement_weights.get(ref_id, 0.0) + value
                achievement_requirements.setdefault(ref_id, set()).add(index)
            elif kind == "H":
                cited_skills.add(ref_id)
            elif kind == "E":
                cited_education.add(ref_id)

    n_functions = len(vacancy.responsibilities)
    for item in evidence_map.functions:
        if not 1 <= item.function <= n_functions:
            continue
        for ref in map(_norm, item.evidence):
            if ref in valid_refs and ref.startswith("L"):
                ref_id = int(ref[1:])
                achievement_weights[ref_id] = achievement_weights.get(ref_id, 0.0) + FUNCTION_WEIGHT
                achievement_requirements.setdefault(ref_id, set()).add(FUNCTION_OFFSET + item.function)

    return MatchResult(
        score=score,
        requirements=matches,
        experience_years=experience_years,
        required_years=vacancy.min_years_experience,
        achievement_weights=achievement_weights,
        achievement_requirements=achievement_requirements,
        cited_skills=cited_skills,
        cited_education=cited_education,
    )
