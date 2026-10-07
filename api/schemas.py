"""Contratos JSON de la API. Validan longitudes y valores permitidos antes de llegar al núcleo."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from core.tracking.models import PLATFORMS, STATUSES, TRIAGE_STATUSES


def _http_or_empty(value: str) -> str:
    if value and not value.startswith(("https://", "http://")):
        raise ValueError("El enlace debe empezar por https:// o http://")
    return value


Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Required = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Url = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(_http_or_empty)]
Status = Literal[tuple(STATUSES)]
ManualStatus = Literal[tuple(s for s in STATUSES if s not in TRIAGE_STATUSES)]
Platform = Literal[("", *PLATFORMS)]


# ── perfil ────────────────────────────────────────────────────────────


class Contact(BaseModel):
    full_name: Text = ""
    email: Text = ""
    phone: Text = ""
    linkedin_url: Url = ""
    github_url: Url = ""


class AchievementOut(BaseModel):
    id: int
    text: str


class ExperienceOut(BaseModel):
    id: int
    role: str
    company: str
    period_text: str
    country: str
    modality: str
    achievements: list[AchievementOut]


class ExperienceIn(BaseModel):
    role: Required
    company: Text = ""
    period_text: Text = ""
    country: Text = ""
    modality: Text = ""
    achievements: list[LongText] = Field(default_factory=list, max_length=60)


class AchievementsIn(BaseModel):
    texts: list[LongText] = Field(min_length=1, max_length=30)


class SkillOut(BaseModel):
    id: int
    name: str
    category: str


class SkillIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)] = "Otros"


class EducationOut(BaseModel):
    id: int
    title: str
    institution: str
    period_text: str
    description: str


class EducationIn(BaseModel):
    title: Required
    institution: Text = ""
    period_text: Text = ""
    description: LongText = ""


class ProfileOut(BaseModel):
    contact: Contact
    experiences: list[ExperienceOut]
    skills: list[SkillOut]
    education: list[EducationOut]
    achievements_with_numbers: int = Field(description="Logros con cifras (los que más pesan en el CV)")
    achievements_total: int


class MeOut(BaseModel):
    email: str
    contact: Contact
    has_experience: bool
    has_skills: bool
    has_education: bool


# ── postulaciones ─────────────────────────────────────────────────────


class ApplicationSummaryOut(BaseModel):
    id: int
    role: str
    company: str
    platform: str
    url: str
    status: str
    status_label: str
    match_score: int | None
    applied_on: date | None
    next_action_on: date | None
    next_action: str
    created_at: datetime
    updated_at: datetime


class EventOut(BaseModel):
    id: int
    kind: str
    from_status: str
    to_status: str
    detail: str
    created_at: datetime


class CVOut(BaseModel):
    id: int
    language: str
    filename: str
    pdf_sha256: str
    sent_at: datetime | None
    created_at: datetime
    intact: bool = Field(description="El PDF y el DOCX coinciden con su huella")


class ApplicationOut(ApplicationSummaryOut):
    contact: str
    vacancy_text: str
    vacancy: dict | None = Field(description="Análisis estructurado de la vacante")
    match: dict | None = Field(description="Resumen de compatibilidad guardado")
    events: list[EventOut]
    cvs: list[CVOut]


class ApplicationIn(BaseModel):
    """Postulación hecha por fuera de la app."""

    role: Required
    company: Text = ""
    platform: Platform = ""
    url: Url = ""
    status: ManualStatus = "postulada"
    applied_on: date | None = None


class DetailsIn(BaseModel):
    role: Required | None = None
    company: Text | None = None
    platform: Platform | None = None
    url: Url | None = None
    contact: Text | None = None


class StatusIn(BaseModel):
    status: Status
    note: LongText = ""


class NoteIn(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class FollowUpIn(BaseModel):
    on: date | None = Field(description="Fecha del recordatorio; null lo quita")
    what: Text = ""


class SentIn(BaseModel):
    cv_id: int | None = Field(default=None, description="CV enviado: debe ser de esta misma postulación")
    sent_on: date | None = None
    platform: Platform = ""


class SummaryOut(BaseModel):
    total: int
    sent: int
    responses: int
    response_rate: float | None
    by_status: dict[str, int]
    due: list[ApplicationSummaryOut]


# ── mercado ───────────────────────────────────────────────────────────


class PlatformStatsOut(BaseModel):
    platform: str
    saved: int
    sent: int
    progressed: int
    rejected: int
    progress_rate: float | None
    avg_score: float | None


class KeywordOut(BaseModel):
    keyword: str
    vacancies: int
    share: float
    owned: bool


class ScoreBucketOut(BaseModel):
    range: str
    sent: int
    progressed: int


class MarketOut(BaseModel):
    applications: int
    analyzed: int
    sent: int
    enough_data: bool
    platforms: list[PlatformStatsOut]
    keywords: list[KeywordOut]
    score_buckets: list[ScoreBucketOut]
