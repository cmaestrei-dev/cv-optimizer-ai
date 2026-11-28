"""Etapa 3 — selección determinista de contenido.

Mochila voraz con diversidad (MMR): cada logro "cuesta" las líneas que ocupa y "vale" según los
requisitos que respalda; se penaliza repetir requisitos ya cubiertos. El ajuste exacto a una página
se hace después, midiendo el PDF real (render.py).
"""

import math
import re
from dataclasses import dataclass, field

from config import SKILL_CATEGORIES
from core.engine import skill_groups as tech
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

CHARS_PER_LINE = 100  # a 10 pt en una hoja carta con márgenes de 0,6 in
_WORD = re.compile(r"[a-z0-9áéíóúñü+#]{3,}")
# Palabras que no dicen de qué trata un logro (para comparar dos logros entre sí).
_STOPWORDS = {"con", "los", "las", "del", "para", "por", "que", "una", "uno", "sus", "como", "más", "mas", "sin", "entre",
              "desde", "sobre", "cada", "todo", "toda", "todos", "todas", "the", "and", "for", "with", "from"}


@dataclass
class Budget:
    max_experiences: int = 4
    max_bullets: int = 18
    min_bullets: int = 10  # una hoja llena rinde más que una medio vacía; el ajuste medido recorta si no cabe
    # 4 viñetas por experiencia (o todas las que tenga) y 5 en las más relevantes, en una página: lo pidió el dueño
    # el 2026-11-28. Con menos, la experiencia parece vacía; el ajuste medido quita antes cursos y habilidades.
    min_bullets_per_experience: int = 4
    max_bullets_per_experience: int = 5
    line_budget: int = 24
    max_education: int = 5  # los títulos y 3 cursos; al recortar quedan los 2 cursos más relevantes
    max_skills: int = 14  # lo que pide la vacante primero; el resto completa (más, y salen herramientas que no vienen al caso)
    redundancy_penalty: float = 0.5
    similarity_penalty: float = 0.6  # dos logros que cuentan lo mismo («integré Wompi» / «verifiqué los webhooks de Wompi»)


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


def _content(text: str) -> set[str]:
    return _tokens(text) - _STOPWORDS


def _similarity(a: AchievementSnap, b: AchievementSnap) -> float:
    """Cuánto se parecen dos logros por sus palabras (0 a 1)."""
    x, y = _content(a.text), _content(b.text)
    return len(x & y) / len(x | y) if x and y else 0.0


def _relevance(exp: ExperienceSnap, scores: dict[int, float]) -> float:
    return sum(sorted((scores[a.id] for a in exp.achievements), reverse=True)[:3])


def _choose_experiences(profile: ProfileSnapshot, scores: dict[int, float], budget: Budget) -> list[ExperienceSnap]:
    experiences = [e for e in profile.experiences if e.achievements]  # sin logros no hay qué mostrar
    if not experiences:
        return []

    chosen = [experiences[0]]  # la más reciente siempre: evita huecos inexplicados
    # Las demás, de la más relevante a la menos, hasta el máximo: una experiencia poco relacionada igual muestra
    # trayectoria, y una hoja medio vacía rinde menos que una llena. Si no cabe, el ajuste medido a 1 página
    # quita primero cursos, habilidades y viñetas de más (document._trim_once) y al final la experiencia más antigua.
    for exp in sorted(experiences[1:], key=lambda e: _relevance(e, scores), reverse=True)[: budget.max_experiences - 1]:
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

    def gain(pair: tuple[ExperienceSnap, AchievementSnap]) -> float:
        exp, a = pair
        reqs = match.achievement_requirements.get(a.id, set())
        redundancy = len(reqs & covered) / len(reqs) if reqs else 0.0
        similar = max((_similarity(a, b) for b in chosen[exp.id]), default=0.0)
        balance = 0.05 if len(chosen[exp.id]) < 2 else 0.0  # 2ª viñeta antes que la 5ª del mismo cargo
        return (scores[a.id] * (1 - budget.redundancy_penalty * redundancy) * (1 - budget.similarity_penalty * similar)
                + balance)

    def remaining(exp: ExperienceSnap) -> list[tuple[ExperienceSnap, AchievementSnap]]:
        return [(exp, a) for a in exp.achievements if a not in chosen[exp.id]]

    # 1) el mejor logro de cada experiencia elegida
    for exp in experiences:
        take(exp, max(exp.achievements, key=lambda a: scores[a.id]))

    # 2) por turnos, hasta el mínimo por experiencia (la más relevante primero, por si se acaba el cupo)
    by_relevance = sorted(experiences, key=lambda e: _relevance(e, scores), reverse=True)
    for _ in range(budget.min_bullets_per_experience - 1):
        for exp in by_relevance:
            if total >= budget.max_bullets or len(chosen[exp.id]) >= budget.max_bullets_per_experience:
                continue
            if options := remaining(exp):
                take(*max(options, key=gain))

    # 3) MMR: el que más aporta, penalizando requisitos ya cubiertos y logros parecidos
    candidates = [pair for exp in experiences for pair in remaining(exp)]
    while candidates and total < budget.max_bullets:
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
    order = {c: i for i, c in enumerate([*tech.ORDER, *SKILL_CATEGORIES])}
    groups: dict[str, list[SkillSnap]] = {}
    for skill in ranked:
        groups.setdefault(tech.display_category(skill.name, skill.category), []).append(skill)
    return sorted(groups.items(), key=lambda g: (min(priority(s) for s in g[1]), order.get(g[0], len(order))))


# Títulos de educación formal (para cualquier profesión) frente a cursos y certificados.
_DEGREE = re.compile(
    r"\b(ingenier[ií]a|ingenier[oa]|licenciatura|licenciad[oa]|tecn[oó]log[oa]|t[eé]cnic[oa] (en|profesional)|"
    r"profesional en|pregrado|carrera|maestr[ií]a|mag[ií]ster|especializaci[oó]n|especialista en|doctorado|"
    r"bachiller|bachillerato|bachelor|master|mba|degree|grado en|administrador[a]? de|contador[a]? p[uú]blic[oa]|"
    r"abogad[oa]|m[eé]dic[oa]|enfermer[oa]|psic[oó]log[oa]|economista|arquitect[oa])\b", re.I)
_COURSE = re.compile(r"\b(certificad[oa]|certificaci[oó]n|certificate|curso|course|bootcamp|diplomado|taller|"
                     r"seminario|career path|ruta de aprendizaje)\b", re.I)


def is_degree_title(title: str) -> bool:
    return bool(_DEGREE.search(title)) and not _COURSE.search(title)


def is_degree(education: EducationSnap) -> bool:
    return is_degree_title(education.title)


def _select_education(profile: ProfileSnapshot, match: MatchResult, budget: Budget) -> list[EducationSnap]:
    # El título formal va siempre (aunque no tenga fechas ni lo cite el análisis); luego lo citado y lo reciente.
    ranked = sorted(profile.education,
                    key=lambda e: (not is_degree(e), e.id not in match.cited_education, -e.period.sort_key[0]))
    chosen = {e.id for e in ranked[: budget.max_education]}
    # Los títulos primero, en el orden del perfil; luego los cursos del más al menos relevante: al recortar para caber
    # en la página se quita el último.
    degrees = [e for e in profile.education if e.id in chosen and is_degree(e)]
    return degrees + [e for e in ranked if e.id in chosen and not is_degree(e)]
