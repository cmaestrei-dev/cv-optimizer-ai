"""Contratos JSON de la API. Validan longitudes y valores permitidos antes de llegar al núcleo."""

from datetime import date, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from core.profile.links import with_scheme
from core.tracking.models import PLATFORMS, STATUSES, TRIAGE_STATUSES


def _http_or_empty(value: str) -> str:
    if not value:
        return value
    value = with_scheme(value)
    if not value.startswith(("https://", "http://")):
        raise ValueError("El enlace debe empezar por https:// o http://")
    try:
        parsed = urlsplit(value)
        if not parsed.hostname:
            raise ValueError("El enlace no es válido")
        _ = parsed.port  # lanza ValueError si el puerto no es válido
    except ValueError as e:
        raise ValueError("El enlace no es válido") from e
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
    """Entrada: valida los enlaces (acepta "www.linkedin.com/in/..." y le agrega https://)."""

    full_name: Text = ""
    email: Text = ""
    phone: Text = ""
    linkedin_url: Url = ""
    github_url: Url = ""


class ContactOut(BaseModel):
    """Salida: tal como está guardado (perfiles de Streamlit o importados pueden tener otros formatos)."""

    full_name: str
    email: str
    phone: str
    linkedin_url: str
    github_url: str


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
    contact: ContactOut
    experiences: list[ExperienceOut]
    skills: list[SkillOut]
    education: list[EducationOut]
    achievements_with_numbers: int = Field(description="Logros con cifras (los que más pesan en el CV)")
    achievements_total: int


class LinkLegacyIn(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class MeOut(BaseModel):
    email: str
    contact: ContactOut
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
    missing_musts: list[str] = Field(default_factory=list, description="Requisitos obligatorios que no cumples")
    partial_musts: list[str] = Field(default_factory=list, description="Obligatorios que cumples a medias")


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


# ── motor: vacantes, análisis, CV y ayudas ────────────────────────────


class VacancyIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20000)] = ""
    url: Url = ""
    prepare: bool = Field(default=False, description="true: lista para postular; false: a la bandeja")


class EvidenceOut(BaseModel):
    ref: str
    label: str


class RequirementOut(BaseModel):
    index: int
    text: str
    kind: str
    category: str
    level: str = Field(description="cubre | parcial | no")
    note: str
    evidence: list[EvidenceOut]


class MatchOut(BaseModel):
    score: int
    experience_years: float
    required_years: float | None
    meets_years: bool | None
    requirements: list[RequirementOut]


class AnalysisOut(BaseModel):
    application_id: int
    status: str
    vacancy: dict
    match: MatchOut | None = Field(description="null: nunca se calculó (POST /applications/{id}/analysis)")
    stale: bool = Field(description="Tu perfil cambió desde el análisis: actualízalo antes de generar")


class GenerateCVIn(BaseModel):
    focus: Text = ""


class JobOut(BaseModel):
    id: int
    kind: str
    status: str = Field(description="queued | running | done | failed")
    result: dict | None
    error: str
    created_at: datetime
    finished_at: datetime | None


class InboxIn(BaseModel):
    links: Annotated[str, StringConstraints(max_length=20000)] = Field(description="Enlaces, uno por línea o mezclados")


class InboxOut(BaseModel):
    job: JobOut
    accepted: list[str]
    skipped: int = Field(description="Enlaces de más (se procesan 10 por carga)")


class CVBulletEdit(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
    included: bool = True


class CVExperienceEdit(BaseModel):
    bullets: list[CVBulletEdit] = Field(max_length=40)


class CVEditIn(BaseModel):
    summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
    experiences: list[CVExperienceEdit] = Field(max_length=30)


class CVResultOut(BaseModel):
    cv_id: int
    filename: str
    pages: int
    trimmed: list[str] = Field(description="Lo que se quitó para caber en 1 página")


class CVDetailOut(CVOut):
    application_id: int
    markdown: str
    document: dict | None = Field(description="Documento estructurado (null: CV anterior a la edición)")


class ScreeningIn(BaseModel):
    questions: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]] = Field(
        min_length=1, max_length=15)


class ScreeningAnswerOut(BaseModel):
    question: str
    answer: str
    needs_you: bool
    note: str


class CoverOut(BaseModel):
    text: str
    fallback: bool = Field(description="La IA inventó algo y se usó un mensaje con solo datos reales")
    problems: list[str]


class GapIn(BaseModel):
    requirement: int = Field(ge=0, description="Índice del requisito (0 = el primero)")
    experience_id: int
    story: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)]


class CandidateOut(BaseModel):
    text: str
    problems: list[str]
    duplicate_of: str | None
    suggested: bool = Field(description="Verificado y no repetido (en /gaps: ya se agregó al perfil)")


class GapOut(BaseModel):
    added: int
    candidates: list[CandidateOut]


class AlertsOut(BaseModel):
    enabled: bool = Field(description="El servidor tiene buzón de alertas configurado")
    address: str = Field(description="Dirección de reenvío de la cuenta; vacía si aún no se activó")
    forwarding_code: str = Field(description="Código que Gmail pide para confirmar el reenvío (si llegó)")
    forwarding_from: str
    last_received_at: datetime | None
    received_count: int
    last_summary: str
    analyzing: int = Field(description="Lotes de vacantes de las alertas en análisis ahora")
    waiting: int = Field(description="Vacantes de las alertas que esperan cupo (o la experiencia de la persona)")
    ignored_recently: int = Field(description="Correos que no son alertas llegados en los últimos días (Gmail reenvía de más)")
    gmail_filter: str = Field(description="Búsqueda para el filtro de Gmail que reenvía solo las alertas")
    daily_limit: int


class AlertsCheckOut(BaseModel):
    checked: bool
    messages: int
    alerts: int
    queued: int
    rejected: int


class TitlesOut(BaseModel):
    titles: list[str]


class SearchLinkOut(BaseModel):
    portal: str
    url: str


class UsageOut(BaseModel):
    used_today: int
    daily_limit: int


# ── perfil asistido: importar, completar, entrevista ──────────────────


class ImportApplyIn(BaseModel):
    experiences: list[int] = Field(default_factory=list, max_length=60, description="Índices de la lectura")
    skills: list[int] = Field(default_factory=list, max_length=200)
    education: list[int] = Field(default_factory=list, max_length=60)
    fill_contact: bool = Field(default=True, description="Completar nombre, correo, teléfono y LinkedIn vacíos")


class ImportApplyOut(BaseModel):
    counts: dict[str, int]
    profile: ProfileOut


class FreeTextIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class TasksOut(BaseModel):
    tasks: list[str]


class TaskItem(BaseModel):
    task: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    detail: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""


class TasksIn(BaseModel):
    items: list[TaskItem] = Field(min_length=1, max_length=20)


class QuestionOut(BaseModel):
    achievement_id: int | None
    question: str
    example: str


class AnswerIn(BaseModel):
    achievement_id: int | None = None
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    answer: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=12)


class ProposalOut(BaseModel):
    achievement_id: int | None = Field(description="Logro que mejora; null si es uno nuevo")
    original: str
    proposed: str
    problems: list[str] = Field(description="Datos que no salen de tus respuestas: no se recomienda aceptarla")


class AcceptedIn(BaseModel):
    achievement_id: int | None = None
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class AcceptIn(BaseModel):
    accepted: list[AcceptedIn] = Field(min_length=1, max_length=30)
    answers: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]] = Field(
        min_length=1, max_length=12, description="Las respuestas de la entrevista: el servidor verifica contra ellas")
