"""Foto inmutable del perfil para el motor de CV: sin ORM ni base de datos, fácil de probar."""

from dataclasses import dataclass, field
from datetime import date

from core.profile.periods import Period


@dataclass(frozen=True)
class AchievementSnap:
    id: int
    text: str


@dataclass(frozen=True)
class ExperienceSnap:
    id: int
    role: str
    company: str
    period_text: str
    period: Period
    country: str = ""
    modality: str = ""
    achievements: tuple[AchievementSnap, ...] = ()


@dataclass(frozen=True)
class SkillSnap:
    id: int
    name: str
    category: str


@dataclass(frozen=True)
class EducationSnap:
    id: int
    title: str
    institution: str
    period_text: str
    period: Period
    description: str = ""


@dataclass(frozen=True)
class ProfileSnapshot:
    username: str
    full_name: str = ""
    experiences: tuple[ExperienceSnap, ...] = ()  # de la más reciente a la más antigua
    skills: tuple[SkillSnap, ...] = ()
    education: tuple[EducationSnap, ...] = ()
    _achievement_index: dict = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self):
        index = {a.id: (exp, a) for exp in self.experiences for a in exp.achievements}
        object.__setattr__(self, "_achievement_index", index)

    def achievement(self, achievement_id: int) -> tuple[ExperienceSnap, AchievementSnap] | None:
        return self._achievement_index.get(achievement_id)

    def total_experience_months(self, today: date | None = None) -> int:
        """Meses de experiencia sin contar dos veces los periodos que se solapan."""
        today = today or date.today()
        months: set[int] = set()
        for exp in self.experiences:
            p = exp.period
            if p.start_year is None:
                continue
            start = p.start_year * 12 + (p.start_month or 1) - 1
            if p.is_current:
                end = today.year * 12 + today.month - 1
            elif p.end_year is not None:
                end = p.end_year * 12 + (p.end_month or 12) - 1
            else:
                end = start + 11 if p.start_month is None else start
            months.update(range(start, end + 1))
        return len(months)
