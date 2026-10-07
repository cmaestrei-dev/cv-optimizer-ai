"""Motor por API: vacantes, análisis, bandeja por lotes, CV (generar y editar), preguntas, mensaje y brechas.

Lo lento va a la cola de trabajos (`/jobs/{id}` para seguirlo). Toda llamada a la IA se cuenta
contra el cupo diario de la cuenta.
"""

import json

from fastapi import APIRouter, status

from api.auth import CurrentAccount
from api.routers.applications import _detail
from api.schemas import (
    AnalysisOut,
    ApplicationOut,
    CandidateOut,
    CoverOut,
    CVDetailOut,
    CVEditIn,
    CVResultOut,
    EvidenceOut,
    GapIn,
    GapOut,
    GenerateCVIn,
    InboxIn,
    InboxOut,
    JobOut,
    MatchOut,
    RequirementOut,
    ScreeningAnswerOut,
    ScreeningIn,
    SearchLinkOut,
    TitlesOut,
    UsageOut,
    VacancyIn,
)
from core import applying, discovery, usage
from core import llm as llm_module
from core.errors import UserInputError
from core.jobs import service as jobs
from core.jobs.models import Job
from core.profile import service as profiles
from core.profile.snapshot import ProfileSnapshot
from core.tracking import service as tracking

router = APIRouter(tags=["motor"])


def _llm(task: str, account: CurrentAccount):
    return usage.metered(llm_module.get_llm(task), account.username)


def _label(ref: str, snapshot: ProfileSnapshot) -> str | None:
    kind, ref_id = ref[0], int(ref[1:])
    if kind == "L" and (found := snapshot.achievement(ref_id)):
        experience, achievement = found
        text = achievement.text if len(achievement.text) <= 90 else achievement.text[:90] + "…"
        return f"«{text}» ({experience.role})"
    if kind == "H":
        return next((f"Habilidad: {s.name}" for s in snapshot.skills if s.id == ref_id), None)
    if kind == "E":
        return next((e.title for e in snapshot.education if e.id == ref_id), None)
    return None


def _analysis(loaded: applying.Loaded) -> AnalysisOut:
    match = None
    if loaded.analysis is not None:
        m = loaded.analysis.match
        match = MatchOut(
            score=m.score, experience_years=m.experience_years, required_years=m.required_years,
            meets_years=m.meets_years,
            requirements=[
                RequirementOut(
                    index=i, text=r.requirement.text, kind=r.requirement.kind, category=r.requirement.category,
                    level=r.level, note=r.note,
                    evidence=[EvidenceOut(ref=ref, label=label) for ref in r.evidence
                              if (label := _label(ref, loaded.snapshot))],
                )
                for i, r in enumerate(m.requirements)
            ],
        )
    return AnalysisOut(application_id=loaded.application.id, status=loaded.application.status,
                       vacancy=loaded.vacancy.model_dump(), match=match, stale=loaded.stale)


def _job(job: Job) -> JobOut:
    try:
        result = json.loads(job.result) if job.result else None
    except json.JSONDecodeError:
        result = None
    return JobOut(id=job.id, kind=job.kind, status=job.status, result=result, error=job.error,
                  created_at=job.created_at, finished_at=job.finished_at)


# ── vacantes y análisis ───────────────────────────────────────────────


@router.post("/vacancies", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def add_vacancy(body: VacancyIn, account: CurrentAccount) -> ApplicationOut:
    """Trae (enlace) o recibe (texto) una vacante, la analiza y la guarda. 409 si ya la tienes."""
    usage.check(account.username)
    application_id = applying.add_vacancy(account.username, _llm("extract", account), text=body.text, url=body.url,
                                          prepare=body.prepare)
    return _detail(account.username, application_id)


@router.get("/applications/{application_id}/analysis", response_model=AnalysisOut)
def get_analysis(application_id: int, account: CurrentAccount) -> AnalysisOut:
    """Compatibilidad con el perfil actual, sin IA (recalculada con las evidencias guardadas)."""
    return _analysis(applying.load(account.username, application_id))


@router.post("/applications/{application_id}/analysis", response_model=AnalysisOut)
def refresh_analysis(application_id: int, account: CurrentAccount) -> AnalysisOut:
    """Vuelve a buscar evidencias con la IA (tras cambiar el perfil)."""
    usage.check(account.username)
    return _analysis(applying.refresh(account.username, application_id, _llm("extract", account)))


@router.post("/applications/{application_id}/prepare", response_model=AnalysisOut)
def prepare(application_id: int, account: CurrentAccount) -> AnalysisOut:
    """«Preparar postulación» desde la bandeja."""
    usage.check(account.username)
    return _analysis(applying.prepare(account.username, application_id, _llm("extract", account)))


# ── bandeja por lotes y descubrimiento ────────────────────────────────


@router.post("/inbox", response_model=InboxOut, status_code=status.HTTP_202_ACCEPTED)
def add_to_inbox(body: InboxIn, account: CurrentAccount) -> InboxOut:
    urls = discovery.parse_links(body.links)
    if not urls:
        raise UserInputError("No encontramos enlaces. Deben empezar por https:// o http://")
    if not profiles.snapshot(account.username).experiences:
        raise UserInputError("Registra primero tu experiencia: sin ella no hay con qué comparar las vacantes.")
    usage.check(account.username)
    accepted = urls[: discovery.MAX_BATCH]
    job_id = jobs.enqueue(account.username, "bandeja", {"urls": accepted})
    return InboxOut(job=_job(jobs.get(account.username, job_id)), accepted=accepted, skipped=len(urls) - len(accepted))


@router.get("/discovery/titles", response_model=TitlesOut)
def suggest_titles(account: CurrentAccount) -> TitlesOut:
    snapshot = profiles.snapshot(account.username)
    if not snapshot.experiences:
        raise UserInputError("Registra primero tu experiencia para sugerirte cargos.")
    usage.check(account.username)
    return TitlesOut(titles=discovery.suggest_titles(_llm("extract", account), snapshot))


@router.get("/discovery/links", response_model=list[SearchLinkOut])
def search_links(title: str, account: CurrentAccount, city: str = "") -> list[SearchLinkOut]:
    return [SearchLinkOut(portal=name, url=url) for name, url in discovery.search_links(title[:100], city[:60])]


# ── CV ────────────────────────────────────────────────────────────────


@router.post("/applications/{application_id}/cvs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def generate_cv(application_id: int, body: GenerateCVIn, account: CurrentAccount) -> JobOut:
    """Genera el CV en segundo plano; el resultado (`cv_id`) aparece en el trabajo."""
    applying.load(account.username, application_id)  # 404 / 422 ahora, no dentro del trabajo
    usage.check(account.username)
    job_id = jobs.enqueue(account.username, "cv", {"application_id": application_id, "focus": body.focus})
    return _job(jobs.get(account.username, job_id))


@router.get("/cvs/{cv_id}", response_model=CVDetailOut)
def get_cv(cv_id: int, account: CurrentAccount) -> CVDetailOut:
    record = tracking.get_cv(account.username, cv_id)
    return CVDetailOut(
        id=record.id, application_id=record.application_id, language=record.language, filename=record.filename,
        pdf_sha256=record.pdf_sha256, sent_at=record.sent_at, created_at=record.created_at,
        intact=tracking.verify_cv(record), markdown=record.markdown,
        document=json.loads(record.document_json) if record.document_json else None,
    )


@router.put("/cvs/{cv_id}/document", response_model=CVResultOut, status_code=status.HTTP_201_CREATED)
def edit_cv(cv_id: int, body: CVEditIn, account: CurrentAccount) -> CVResultOut:
    """Guarda una versión nueva del CV con las ediciones; el original no se toca. Cuenta en el cupo diario
    como una llamada (no usa IA, pero genera y guarda un PDF nuevo)."""
    usage.check(account.username)
    result = applying.edit_cv(
        account.username, cv_id, summary=body.summary,
        bullets=[[(b.text, b.included) for b in exp.bullets] for exp in body.experiences],
    )
    usage.add(account.username)
    return CVResultOut(**result)


# ── ayudas para postular ──────────────────────────────────────────────


@router.post("/applications/{application_id}/screening", response_model=list[ScreeningAnswerOut])
def screening(application_id: int, body: ScreeningIn, account: CurrentAccount) -> list[ScreeningAnswerOut]:
    usage.check(account.username)
    answers = applying.screening(account.username, application_id, body.questions, _llm("write", account))
    return [ScreeningAnswerOut(question=a.question, answer=a.answer, needs_you=a.needs_you, note=a.note) for a in answers]


@router.post("/applications/{application_id}/cover", response_model=CoverOut)
def cover(application_id: int, account: CurrentAccount) -> CoverOut:
    usage.check(account.username)
    note = applying.cover_note(account.username, application_id, write_llm=_llm("write", account),
                               extract_llm=_llm("extract", account))
    return CoverOut(text=note.text, fallback=note.fallback, problems=note.problems)


@router.post("/applications/{application_id}/gaps", response_model=GapOut)
def gap(application_id: int, body: GapIn, account: CurrentAccount) -> GapOut:
    """«Sí lo he hecho»: lo contado sobre un requisito faltante se agrega como logros verificados."""
    usage.check(account.username)
    added, candidates = applying.gap_story(account.username, application_id, body.requirement, body.experience_id,
                                           body.story, _llm("extract", account))
    return GapOut(added=added, candidates=[
        CandidateOut(text=c.text, problems=c.problems, duplicate_of=c.duplicate_of, added=c.suggested)
        for c in candidates
    ])


# ── trabajos y uso ────────────────────────────────────────────────────


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, account: CurrentAccount) -> JobOut:
    return _job(jobs.get(account.username, job_id))


@router.get("/usage", response_model=UsageOut)
def get_usage(account: CurrentAccount) -> UsageOut:
    return UsageOut(used_today=usage.used_today(account.username), daily_limit=usage.daily_limit())
