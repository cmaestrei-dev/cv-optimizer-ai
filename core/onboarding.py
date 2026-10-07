"""Perfil asistido para la API: importar el CV o el PDF de LinkedIn, completar la experiencia y
entrevista guiada. Mismas garantías que en Streamlit: la IA solo copia (al importar) o propone; todo
se verifica contra el PDF o contra las palabras de la persona, y solo se guarda lo que ella acepta.
"""

from pydantic import ValidationError

from core.engine.verification import unsupported
from core.errors import UserInputError
from core.jobs import service as jobs
from core.llm.client import LLMClient
from core.profile import service as profiles
from core.profile.completion import (
    Candidate,
    merge_task_details,
    split_into_achievements,
    typical_tasks,
)
from core.profile.importer import ImportedCV, extract_cv, plan_import
from core.profile.interview import (
    CheckedProposal,
    Question,
    generate_questions,
    merge_achievements,
    propose_improvements,
)
from core.profile.repository import NotFoundError
from core.profile.snapshot import ExperienceSnap
from utils.pdf_extractor import extract_text_from_pdf

MAX_PDF_BYTES = 5_000_000
MAX_PDF_TEXT = 30_000  # lo que lee la IA (core/profile/importer.py)


# ── importar CV / LinkedIn ────────────────────────────────────────────


def start_import(username: str, pdf: bytes) -> int:
    """Lee el texto del PDF y encola su lectura con la IA. Devuelve el id del trabajo."""
    if len(pdf) > MAX_PDF_BYTES:
        raise UserInputError("El PDF pesa más de 5 MB.")
    if not pdf.startswith(b"%PDF"):
        raise UserInputError("El archivo no es un PDF.")
    text = extract_text_from_pdf(pdf)
    if not text or len(text.strip()) < 50:
        raise UserInputError(
            "No encontramos texto en ese PDF (¿es una foto o un escaneo?). Usa el PDF que exporta LinkedIn "
            "o tu CV guardado como PDF desde Word o Google Docs."
        )
    return jobs.enqueue(username, "importar", {"pdf_text": text[:MAX_PDF_TEXT]})


def read_import(username: str, pdf_text: str, llm: LLMClient) -> dict:
    """Trabajo "importar": la IA copia los datos; el código descarta lo que no está en el PDF y lo repetido."""
    imported = extract_cv(llm, pdf_text)
    plan = plan_import(imported, pdf_text, profiles.snapshot(username))  # filtra `imported` en el lugar
    return {
        "data": imported.model_dump(), "new_experiences": plan.new_experiences,
        "duplicate_experiences": plan.duplicate_experiences, "new_skills": plan.new_skills,
        "new_education": plan.new_education, "discarded": plan.discarded, "applied": False,
    }


def apply_import(
    username: str, job_id: int, *, experiences: list[int], skills: list[int], education: list[int], fill_contact: bool
) -> dict[str, int]:
    """Guarda lo elegido de una lectura terminada, una sola vez y en una sola transacción.

    Se usa lo que leyó el servidor (el resultado del trabajo), nunca datos enviados por el cliente.
    """
    def apply(session, result: dict) -> dict:
        offered = (set(result.get("new_experiences", [])), set(result.get("new_skills", [])),
                   set(result.get("new_education", [])))
        if not (set(experiences) <= offered[0] and set(skills) <= offered[1] and set(education) <= offered[2]):
            raise UserInputError("La selección no corresponde a esta lectura del CV.")
        try:
            data = ImportedCV.model_validate(result["data"])
        except (KeyError, ValidationError):
            raise UserInputError("Esta lectura del CV ya no se puede usar. Vuelve a subir el PDF.") from None
        return profiles.apply_import_in(session, username, data, experiences=experiences, skills=skills,
                                        education=education, fill_contact=fill_contact)

    return jobs.apply_import_result(username, job_id, apply)


# ── completar la experiencia ──────────────────────────────────────────


def experience(username: str, experience_id: int) -> ExperienceSnap:
    found = next((e for e in profiles.snapshot(username).experiences if e.id == experience_id), None)
    if found is None:
        raise NotFoundError(f"Experiencia {experience_id}")
    return found


def from_text(username: str, experience_id: int, text: str, llm: LLMClient) -> list[Candidate]:
    """«Cuéntame todo lo que hacías»: texto libre → logros separados y verificados (no se guardan aún)."""
    return split_into_achievements(llm, experience(username, experience_id), text)


def tasks(username: str, experience_id: int, llm: LLMClient) -> list[str]:
    """Tareas típicas del cargo, como recordatorio: la persona marca solo las que sí hizo."""
    return typical_tasks(llm, experience(username, experience_id))


def from_tasks(username: str, experience_id: int, items: list[tuple[str, str]], llm: LLMClient) -> list[Candidate]:
    """Tareas confirmadas (+ detalle opcional) → logros verificados (no se guardan aún)."""
    return merge_task_details(llm, experience(username, experience_id), items)


# ── entrevista guiada ─────────────────────────────────────────────────


def interview_questions(username: str, experience_id: int, llm: LLMClient) -> list[Question]:
    return generate_questions(llm, experience(username, experience_id))


def interview_proposals(
    username: str, experience_id: int, answers: list[tuple[Question, str]], llm: LLMClient
) -> list[CheckedProposal]:
    return propose_improvements(llm, experience(username, experience_id), answers)


def accept_proposals(username: str, experience_id: int, accepted: list[tuple[int | None, str]], answers: list[str]) -> None:
    """Reemplaza los logros mejorados en su lugar y agrega los nuevos al final.

    El servidor vuelve a verificar cada texto contra el logro original y las respuestas (la misma
    regla de `propose_improvements`): lo que no se respalda no se guarda, sin depender del cliente.
    Para cambios libres están los endpoints del perfil.
    """
    exp = experience(username, experience_id)
    originals = {a.id: a.text for a in exp.achievements}
    all_answers = " ".join(a.strip() for a in answers)
    checked = []
    for aid, text in accepted:
        if aid is not None and aid not in originals:
            raise UserInputError("Uno de esos logros ya no existe en esta experiencia. Recarga y vuelve a intentarlo.")
        original = originals.get(aid, "")
        problems = unsupported(text, f"{original} {all_answers} {exp.role} {exp.company}")
        if problems:
            raise UserInputError(f"«{text[:60]}» incluye datos que no salen de tus respuestas: {'; '.join(problems)}")
        checked.append(CheckedProposal(aid, original, text.strip()))
    profiles.update_experience(username, experience_id, merge_achievements(exp, checked))
