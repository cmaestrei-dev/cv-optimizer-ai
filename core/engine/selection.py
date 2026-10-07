"""Etapa 3 — selección determinista de contenido.

Mochila voraz con diversidad (MMR): cada logro "cuesta" las líneas que ocupa y "vale" según los
requisitos que respalda; se penaliza repetir requisitos ya cubiertos. El ajuste exacto a una página
se hace después, midiendo el PDF real (render.py).
"""

import math
import re
from dataclasses import dataclass, field

from config import SKILL_CATEGORIES
from core.engine.matching import MatchResult
from core.profile.repository import skill_key
from core.profile.snapshot import (
    AchievementSnap,
    EducationSnap,
    ExperienceSnap,
    ProfileSnapshot,
    SkillSnap,
)
from core.vacancy import VacancyAnalysis

CHARS_PER_LINE = 110
_WORD = re.compile(r"[a-z0-9áéíóúñü+#]{3,}")


@dataclass
class Budget:
    max_experiences: int = 3
    max_bullets: int = 12
    min_bullets: int = 8
    max_bullets_per_experience: int = 6
    line_budget: int = 40
    max_education: int = 4
    max_skills: int = 18
    redundancy_penalty: float = 0.5


@dataclass
class SelectedExperience:
    experience: ExperienceSnap
    achievements: list[AchievementSnap] = field(default_factory=list)


@dataclass
class Selection:
    experiences: list[SelectedExperience]
    skill_groups: list[tuple[str, list[SkillSnap]]]
    education: list[EducationSnap]
    scores: dict[int, float]


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(skill_key(text)))


def achievement_scores(profile: ProfileSnapshot, match: MatchResult, vacancy: VacancyAnalysis) -> dict[int, float]:
    keyword_tokens = set().union(*(_tokens(k) for k in vacancy.keywords)) if vacancy.keywords else set()
    n = max(len(profile.experiences), 1)
    scores = {}
    for position, exp in enumerate(profile.experiences):
        recency = 0.05 * (n - position) / n
        for a in exp.achievements:
            overlap = len(_tokens(a.text) & keyword_tokens)
            scores[a.id] = match.achievement_weights.get(a.id, 0.0) + 0.1 * min(overlap, 3) + recency
    return scores


def _lines(a: AchievementSnap) -> int:
    return max(1, math.ceil(len(a.text) / CHARS_PER_LINE))


def _choose_experiences(profile: ProfileSnapshot, scores: dict[int, float], budget: Budget) -> list[ExperienceSnap]:
    experiences = [e for e in profile.experiences if e.achievements]  # sin logros no hay qué mostrar
    if not experiences:
        return []

    def relevance(exp: ExperienceSnap) -> float:
        return sum(sorted((scores[a.id] for a in exp.achievements), reverse=True)[:3])

    chosen = [experiences[0]]  # la más reciente siempre: evita huecos inexplicados
    others = sorted(experiences[1:], key=relevance, reverse=True)
    for exp in others:
        if len(chosen) >= budget.max_experiences:
            break
        if relevance(exp) > 0.1 or len(chosen) < 2:
            chosen.append(exp)
    order = {exp.id: i for i, exp in enumerate(profile.experiences)}
    return sorted(chosen, key=lambda e: order[e.id])


def select_content(
    profile: ProfileSnapshot,
    match: MatchResult,
    vacancy: VacancyAnalysis,
    budget: Budget | None = None,
) -> Selection:
    budget = budget or Budget()
    scores = achievement_scores(profile, match, vacancy)
    experiences = _choose_experiences(profile, scores, budget)

    chosen: dict[int, list[AchievementSnap]] = {e.id: [] for e in experiences}
    covered: set[int] = set()
    lines_used = 0
    total = 0

    def take(exp: ExperienceSnap, a: AchievementSnap) -> None:
        nonlocal lines_used, total
        chosen[exp.id].append(a)
        covered.update(match.achievement_requirements.get(a.id, set()))
        lines_used += _lines(a)
        total += 1

    # 1) el mejor logro de cada experiencia elegida
    for exp in experiences:
        take(exp, max(exp.achievements, key=lambda a: scores[a.id]))

    # 2) MMR: el que más aporta, penalizando requisitos ya cubiertos
    candidates = [(exp, a) for exp in experiences for a in exp.achievements if a not in chosen[exp.id]]
    while candidates and total < budget.max_bullets:
        def gain(pair: tuple[ExperienceSnap, AchievementSnap]) -> float:
            reqs = match.achievement_requirements.get(pair[1].id, set())
            redundancy = len(reqs & covered) / len(reqs) if reqs else 0.0
            balance = 0.05 if len(chosen[pair[0].id]) < 2 else 0.0  # 2ª viñeta antes que la 5ª del mismo cargo
            return scores[pair[1].id] * (1 - budget.redundancy_penalty * redundancy) + balance

        feasible = [
            p for p in candidates
            if len(chosen[p[0].id]) < budget.max_bullets_per_experience
            and lines_used + _lines(p[1]) <= budget.line_budget
        ]
        if not feasible:
            break
        best = max(feasible, key=gain)
        if gain(best) <= 0.06 and total >= budget.min_bullets:
            break  # lo que queda no aporta a esta vacante
        take(*best)
        candidates.remove(best)

    selected = [
        SelectedExperience(exp, [a for a in exp.achievements if a in chosen[exp.id]])  # orden original
        for exp in experiences
    ]
    return Selection(
        experiences=selected,
        skill_groups=_select_skills(profile, match, vacancy, budget),
        education=_select_education(profile, match, budget),
        scores=scores,
    )


def _select_skills(
    profile: ProfileSnapshot, match: MatchResult, vacancy: VacancyAnalysis, budget: Budget
) -> list[tuple[str, list[SkillSnap]]]:
    keyword_keys = {skill_key(k) for k in vacancy.keywords}

    def priority(skill: SkillSnap) -> int:
        if skill.id in match.cited_skills:
            return 0
        if skill_key(skill.name) in keyword_keys:
            return 1
        return 2

    ranked = sorted(profile.skills, key=priority)[: budget.max_skills]
    order = {c: i for i, c in enumerate(SKILL_CATEGORIES)}
    groups: dict[str, list[SkillSnap]] = {}
    for skill in ranked:
        groups.setdefault(skill.category, []).append(skill)
    return sorted(groups.items(), key=lambda g: (min(priority(s) for s in g[1]), order.get(g[0], len(order))))


def _select_education(profile: ProfileSnapshot, match: MatchResult, budget: Budget) -> list[EducationSnap]:
    ranked = sorted(profile.education, key=lambda e: (e.id not in match.cited_education, -e.period.sort_key[0]))
    chosen = {e.id for e in ranked[: budget.max_education]}
    return [e for e in profile.education if e.id in chosen]  # orden cronológico inverso del perfil
