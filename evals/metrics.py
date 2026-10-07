"""Métricas de calidad del motor (puras, sin IA)."""

import time
from dataclasses import dataclass, field

from core.engine.document import SECTION_TITLES
from core.engine.pipeline import Analysis, GeneratedCV
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
    summary_replaced: bool = False
    pages: int = 0
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
    profile_text = skill_key(" ".join(
        [a.text for e in profile.experiences for a in e.achievements]
        + [s.name for s in profile.skills] + [e.title for e in profile.education]
    ))
    cv = skill_key(cv_text)
    owned = [k for k in analysis.vacancy.keywords if skill_key(k) and skill_key(k) in profile_text]
    if not owned:
        return 1.0
    return sum(skill_key(k) in cv for k in owned) / len(owned)


def language_ok(generated: GeneratedCV, expected: str) -> bool:
    titles = SECTION_TITLES.get(expected, SECTION_TITLES["es"])
    return generated.document.to_markdown().startswith(f"## {titles[0]}")
