"""Métricas de calidad del motor (puras, sin IA)."""

import time
from dataclasses import dataclass, field

from core.engine.document import SECTION_TITLES
from core.engine.keywords import coverage
from core.engine.pipeline import Analysis, GeneratedCV
from core.engine.writing import BULLET_MAX, style_problems
from core.profile.repository import skill_key
from core.profile.snapshot import ProfileSnapshot
from evals.cases import Case


class CountingLLM:
    """Envuelve un LLMClient para contar llamadas y tiempo."""

    def __init__(self, llm):
        self._llm = llm
        self.label = llm.label
        self.calls = 0
        self.seconds = 0.0

    def complete(self, prompt, **kwargs):
        self.calls += 1
        start = time.perf_counter()
        try:
            return self._llm.complete(prompt, **kwargs)
        finally:
            self.seconds += time.perf_counter() - start


@dataclass
class CaseResult:
    case: str
    provider: str
    score: int = 0
    match_hits: int = 0
    match_total: int = 0
    match_misses: list[str] = field(default_factory=list)
    bullets: int = 0
    reverted: int = 0
    restyled: int = 0
    summary_replaced: bool = False
    pages: int = 0
    min_bullets: int = 0  # la experiencia con menos viñetas en la hoja final (v3: 4, o todas las que tenga)
    ai_style: int = 0  # viñetas y resumen de la hoja final que aún suenan a IA (debería ser 0)
    long_bullets: int = 0  # viñetas de más de una línea
    language_ok: bool = False
    keyword_coverage: float = 0.0
    llm_calls: int = 0
    seconds: float = 0.0
    error: str = ""


def match_accuracy(case: Case, analysis: Analysis) -> tuple[int, int, list[str]]:
    hits, misses = 0, []
    for word, accepted in case.expected.items():
        key = skill_key(word)
        found = [m for m in analysis.match.requirements if key in skill_key(m.requirement.text)]
        if not found:
            misses.append(f"{word}: la vacante analizada no tiene un requisito con esa palabra")
            continue
        level = found[0].level
        if level in accepted:
            hits += 1
        else:
            misses.append(f"{word}: esperado {'/'.join(sorted(accepted))}, obtenido {level}")
    return hits, len(case.expected), misses


def keyword_coverage(analysis: Analysis, profile: ProfileSnapshot, cv_text: str) -> float:
    """De las palabras clave de la vacante que el candidato SÍ tiene en su perfil, cuántas muestra el CV."""
    report = coverage(cv_text, analysis.vacancy, profile)
    owned = len(report.present) + len(report.missing_owned)
    return len(report.present) / owned if owned else 1.0


def page_stats(generated: GeneratedCV, profile: ProfileSnapshot) -> tuple[int, int, int]:
    """(mínimo de viñetas por experiencia visible, textos que suenan a IA, viñetas largas) en la hoja final."""
    doc = generated.document
    available = {(e.role, e.company, e.period_text): len(e.achievements) for e in profile.experiences}
    originals = {a.id: a.text for e in profile.experiences for a in e.achievements}
    counts, ai, long = [], 0, 0
    for exp in doc.visible_experiences():
        # con menos de 4 logros en el perfil, todas cuentan como el mínimo
        has = available.get((exp.role, exp.company, exp.period_text), 0)
        counts.append(len(exp.included) if len(exp.included) < min(has, 4) else 4)
        for b in exp.included:
            ai += bool(style_problems(b.text, originals.get(b.achievement_id, ""), doc.language))
            long += len(b.text) > BULLET_MAX
    ai += bool(style_problems(doc.summary, "", doc.language))
    return (min(counts) if counts else 0), ai, long


def language_ok(generated: GeneratedCV, expected: str) -> bool:
    titles = SECTION_TITLES.get(expected, SECTION_TITLES["es"])
    return generated.document.to_markdown().startswith(f"## {titles[0]}")
