"""Orquestación del motor: analizar (vacante + match) y generar (selección → redacción → render)."""

import hashlib
import json
from dataclasses import dataclass, field

from core.engine.document import CVDocument, RenderResult, build_document, render
from core.engine.matching import EvidenceMap, MatchResult, build_evidence_map, compute_match
from core.engine.selection import Budget, select_content
from core.engine.writing import write_cv
from core.llm.client import Image, LLMClient
from core.profile.snapshot import ProfileSnapshot
from core.vacancy import VacancyAnalysis, analyze_vacancy
from models import UserProfile


@dataclass
class Analysis:
    vacancy: VacancyAnalysis
    match: MatchResult
    evidence: EvidenceMap | None = None  # lo que propuso la IA; guardarlo permite recalcular sin IA


@dataclass
class GeneratedCV:
    document: CVDocument
    output: RenderResult
    reverted: dict[int, list[str]] = field(default_factory=dict)
    summary_replaced: bool = False


def analyze(
    llm: LLMClient,
    profile: ProfileSnapshot,
    text: str = "",
    images: tuple[Image, ...] = (),
) -> Analysis:
    vacancy = analyze_vacancy(llm, text=text, images=images)
    evidence = build_evidence_map(llm, vacancy, profile)
    return Analysis(vacancy, compute_match(vacancy, evidence, profile), evidence)


def match_only(llm: LLMClient, profile: ProfileSnapshot, vacancy: VacancyAnalysis) -> Analysis:
    """Recalcula el match de una vacante ya analizada contra el perfil actual (1 llamada a la IA)."""
    evidence = build_evidence_map(llm, vacancy, profile)
    return Analysis(vacancy, compute_match(vacancy, evidence, profile), evidence)


def rematch(vacancy: VacancyAnalysis, evidence: EvidenceMap, profile: ProfileSnapshot) -> Analysis:
    """Match determinista desde un mapa de evidencias guardado (sin IA). Las referencias a logros que
    ya no existen se descartan; lo agregado después no cuenta hasta volver a analizar."""
    return Analysis(vacancy, compute_match(vacancy, evidence, profile), evidence)


def profile_fingerprint(profile: ProfileSnapshot) -> str:
    """Cambia cuando cambia algo que la IA usa como evidencia (logros, habilidades, estudios, cargos)."""
    data = [
        [(e.id, e.role, e.period_text, [(a.id, a.text) for a in e.achievements]) for e in profile.experiences],
        [(k.id, k.name) for k in profile.skills],
        [(d.id, d.title, d.institution) for d in profile.education],
    ]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()[:16]


def evidence_json(evidence: EvidenceMap, profile: ProfileSnapshot) -> str:
    return json.dumps({"map": evidence.model_dump(), "profile": profile_fingerprint(profile)}, ensure_ascii=False)


def load_evidence(text: str) -> tuple[EvidenceMap | None, str]:
    """(mapa, huella del perfil con que se calculó). (None, "") si no hay o está dañado."""
    try:
        data = json.loads(text) if text else None
        return EvidenceMap.model_validate(data["map"]), str(data.get("profile", ""))
    except (ValueError, TypeError, KeyError):
        return None, ""


def match_summary(match: MatchResult) -> dict:
    """Resumen serializable del match para guardarlo con la postulación (listas y bandeja)."""
    return {
        "score": match.score,
        "experience_years": match.experience_years,
        "required_years": match.required_years,
        "requirements": [
            {"text": m.requirement.text, "kind": m.requirement.kind, "level": m.level} for m in match.requirements
        ],
    }


def generate(
    llm: LLMClient,
    profile: ProfileSnapshot,
    contact: UserProfile,
    analysis: Analysis,
    *,
    extra_focus: str = "",
    max_pages: int = 1,
    budget: Budget | None = None,
) -> GeneratedCV:
    selection = select_content(profile, analysis.match, analysis.vacancy, budget)
    written = write_cv(llm, analysis.vacancy, selection, analysis.match, profile, extra_focus=extra_focus)
    language = (analysis.vacancy.language or "es").lower()[:2]
    document = build_document(selection, written, language)
    return GeneratedCV(
        document=document,
        output=render(document, contact, max_pages=max_pages),
        reverted=written.reverted,
        summary_replaced=bool(written.summary_problems),
    )
