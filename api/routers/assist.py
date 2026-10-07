"""Perfil asistido: importar el CV o el PDF de LinkedIn, completar la experiencia y entrevista guiada.

Lo que la IA propone vuelve con su verificación; nada se guarda hasta que la persona lo acepta
(con estos endpoints o con los de `profile.py`).
"""

from fastapi import APIRouter, File, UploadFile, status

from api.auth import CurrentAccount
from api.routers.engine import _job, _llm
from api.routers.profile import _profile
from api.schemas import (
    AcceptIn,
    AnswersIn,
    CandidateOut,
    FreeTextIn,
    ImportApplyIn,
    ImportApplyOut,
    JobOut,
    ProfileOut,
    ProposalOut,
    QuestionOut,
    TasksIn,
    TasksOut,
)
from core import onboarding, usage
from core.errors import UserInputError
from core.jobs import service as jobs
from core.profile.completion import Candidate
from core.profile.interview import Question

router = APIRouter(tags=["perfil asistido"])


def _candidates(candidates: list[Candidate]) -> list[CandidateOut]:
    """Propuestas sin guardar: `suggested` = verificada y no repetida (se recomienda aceptarla)."""
    return [CandidateOut(text=c.text, problems=c.problems, duplicate_of=c.duplicate_of, suggested=c.suggested)
            for c in candidates]


@router.post("/profile/import", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def import_cv(account: CurrentAccount, file: UploadFile = File(description="CV o PDF de LinkedIn")) -> JobOut:  # noqa: B008
    """Lee el PDF en segundo plano. El resultado del trabajo trae lo leído, lo descartado y lo repetido.

    Función normal (no async): leer el PDF es trabajo síncrono y así corre en el pool de hilos sin
    detener las demás peticiones.
    """
    pdf = file.file.read(onboarding.MAX_PDF_BYTES + 1)
    usage.check(account.username)
    job_id = onboarding.start_import(account.username, pdf)
    return _job(jobs.get(account.username, job_id))


@router.post("/profile/import/{job_id}/apply", response_model=ImportApplyOut)
def apply_import(job_id: int, body: ImportApplyIn, account: CurrentAccount) -> ImportApplyOut:
    counts = onboarding.apply_import(account.username, job_id, experiences=body.experiences, skills=body.skills,
                                     education=body.education, fill_contact=body.fill_contact)
    return ImportApplyOut(counts=counts, profile=_profile(account.username))


@router.post("/experiences/{experience_id}/suggestions/from-text", response_model=list[CandidateOut])
def from_text(experience_id: int, body: FreeTextIn, account: CurrentAccount) -> list[CandidateOut]:
    """«Cuéntame todo lo que hacías»: texto libre → logros separados y verificados."""
    onboarding.experience(account.username, experience_id)
    usage.check(account.username)
    return _candidates(onboarding.from_text(account.username, experience_id, body.text, _llm("extract", account)))


@router.post("/experiences/{experience_id}/suggestions/tasks", response_model=TasksOut)
def typical_tasks(experience_id: int, account: CurrentAccount) -> TasksOut:
    """Tareas típicas del cargo para marcar las que sí hiciste."""
    onboarding.experience(account.username, experience_id)
    usage.check(account.username)
    return TasksOut(tasks=onboarding.tasks(account.username, experience_id, _llm("extract", account)))


@router.post("/experiences/{experience_id}/suggestions/from-tasks", response_model=list[CandidateOut])
def from_tasks(experience_id: int, body: TasksIn, account: CurrentAccount) -> list[CandidateOut]:
    onboarding.experience(account.username, experience_id)
    if any(item.detail for item in body.items):  # sin detalles no se usa la IA
        usage.check(account.username)
    items = [(item.task, item.detail) for item in body.items]
    return _candidates(onboarding.from_tasks(account.username, experience_id, items, _llm("extract", account)))


@router.post("/experiences/{experience_id}/interview/questions", response_model=list[QuestionOut])
def interview_questions(experience_id: int, account: CurrentAccount) -> list[QuestionOut]:
    onboarding.experience(account.username, experience_id)
    usage.check(account.username)
    questions = onboarding.interview_questions(account.username, experience_id, _llm("extract", account))
    return [QuestionOut(achievement_id=q.achievement_id, question=q.question, example=q.example) for q in questions]


@router.post("/experiences/{experience_id}/interview/proposals", response_model=list[ProposalOut])
def interview_proposals(experience_id: int, body: AnswersIn, account: CurrentAccount) -> list[ProposalOut]:
    onboarding.experience(account.username, experience_id)
    if not any(a.answer for a in body.answers):
        raise UserInputError("Responde al menos una pregunta.")
    usage.check(account.username)
    answers = [(Question(achievement_id=a.achievement_id, question=a.question), a.answer) for a in body.answers]
    proposals = onboarding.interview_proposals(account.username, experience_id, answers, _llm("write", account))
    return [ProposalOut(achievement_id=p.achievement_id, original=p.original, proposed=p.proposed, problems=p.problems)
            for p in proposals]


@router.post("/experiences/{experience_id}/interview/accept", response_model=ProfileOut)
def interview_accept(experience_id: int, body: AcceptIn, account: CurrentAccount) -> ProfileOut:
    """Aplica las mejoras elegidas: reemplaza cada logro mejorado en su lugar y agrega los nuevos."""
    onboarding.accept_proposals(account.username, experience_id, [(a.achievement_id, a.text) for a in body.accepted],
                                body.answers)
    return _profile(account.username)
