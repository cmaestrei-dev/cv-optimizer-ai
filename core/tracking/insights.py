"""Analítica "Mi mercado": qué piden las vacantes y qué consigue respuesta, por portal.

Solo usa datos propios del usuario (sus postulaciones guardadas). Todo es determinista.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from pydantic import ValidationError

from core.profile.repository import skill_key
from core.profile.snapshot import ProfileSnapshot
from core.tracking.models import APPLIED_STATUSES, Application
from core.vacancy import VacancyAnalysis

PROGRESS_STATUSES = ("en_revision", "entrevista", "oferta")  # avanzó tras enviar
MIN_FOR_TRENDS = 5  # por debajo de esto los porcentajes todavía no dicen mucho
SCORE_BUCKETS = ((0, 49, "Menos de 50"), (50, 74, "50 a 74"), (75, 100, "75 o más"))


@dataclass
class PlatformStats:
    platform: str
    saved: int = 0
    sent: int = 0
    progressed: int = 0
    rejected: int = 0
    scores: list[int] = field(default_factory=list)

    @property
    def progress_rate(self) -> float | None:
        return self.progressed / self.sent if self.sent else None

    @property
    def avg_score(self) -> float | None:
        return sum(self.scores) / len(self.scores) if self.scores else None


@dataclass
class KeywordStat:
    keyword: str
    vacancies: int
    share: float
    owned: bool


@dataclass
class Insights:
    applications: int
    analyzed: int
    sent: int
    platforms: list[PlatformStats]
    keywords: list[KeywordStat]
    score_buckets: list[tuple[str, int, int]]  # (rango, enviadas, avanzaron)

    @property
    def enough_data(self) -> bool:
        return self.sent >= MIN_FOR_TRENDS

    @property
    def top_gaps(self) -> list[KeywordStat]:
        return [k for k in self.keywords if not k.owned]


def _vacancy(application: Application) -> VacancyAnalysis | None:
    if not application.analysis_json:
        return None
    try:
        return VacancyAnalysis.model_validate_json(application.analysis_json)
    except ValidationError:
        return None


def profile_text_key(profile: ProfileSnapshot) -> str:
    parts = [a.text for e in profile.experiences for a in e.achievements]
    parts += [s.name for s in profile.skills] + [f"{e.title} {e.institution}" for e in profile.education]
    parts += [e.role for e in profile.experiences]
    return f" {skill_key(' '.join(parts))} "


def build_insights(applications: list[Application], profile: ProfileSnapshot, *, platform: str | None = None,
                   top: int = 15) -> Insights:
    selected = [a for a in applications if platform is None or (a.platform or "Sin plataforma") == platform]
    by_platform: dict[str, PlatformStats] = {}
    keyword_counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    buckets = {label: [0, 0] for _, _, label in SCORE_BUCKETS}
    analyzed = 0

    for a in selected:
        stats = by_platform.setdefault(a.platform or "Sin plataforma", PlatformStats(a.platform or "Sin plataforma"))
        stats.saved += 1
        sent = a.status in APPLIED_STATUSES
        stats.sent += sent
        stats.progressed += a.status in PROGRESS_STATUSES
        stats.rejected += a.status == "rechazada"
        if a.match_score is not None:
            stats.scores.append(a.match_score)
            if sent:
                label = next(lbl for lo, hi, lbl in SCORE_BUCKETS if lo <= a.match_score <= hi)
                buckets[label][0] += 1
                buckets[label][1] += a.status in PROGRESS_STATUSES

        vacancy = _vacancy(a)
        if vacancy is None:
            continue
        analyzed += 1
        seen: set[str] = set()
        for keyword in vacancy.keywords:
            key = skill_key(keyword)
            if key and key not in seen:
                seen.add(key)
                keyword_counts[key] += 1
                display.setdefault(key, keyword.strip())

    owned_text = profile_text_key(profile)
    keywords = [
        KeywordStat(display[key], count, count / analyzed if analyzed else 0.0, f" {key} " in owned_text)
        for key, count in keyword_counts.most_common(top)
    ]
    return Insights(
        applications=len(selected),
        analyzed=analyzed,
        sent=sum(s.sent for s in by_platform.values()),
        platforms=sorted(by_platform.values(), key=lambda s: (-s.sent, -s.saved, s.platform)),
        keywords=keywords,
        score_buckets=[(label, sent, progressed) for label, (sent, progressed) in buckets.items()],
    )


def platforms_in(applications: list[Application]) -> list[str]:
    return sorted({a.platform or "Sin plataforma" for a in applications})


def area_breakdown(applications: list[Application]) -> dict[str, int]:
    areas: defaultdict[str, int] = defaultdict(int)
    for a in applications:
        vacancy = _vacancy(a)
        if vacancy and vacancy.area:
            areas[vacancy.area.strip().capitalize()] += 1
    return dict(sorted(areas.items(), key=lambda kv: -kv[1]))
