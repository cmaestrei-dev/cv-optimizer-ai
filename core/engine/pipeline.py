"""Orquestación del motor: analizar (vacante + match) y generar (selección → redacción → render)."""

from dataclasses import dataclass, field

from core.engine.document import CVDocument, RenderResult, build_document, render
from core.engine.matching import MatchResult, build_evidence_map, compute_match
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
    return Analysis(vacancy, compute_match(vacancy, evidence, profile))


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
