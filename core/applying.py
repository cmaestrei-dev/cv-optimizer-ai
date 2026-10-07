"""Casos de uso de la postulación asistida (los usa la API): vacante → análisis → CV → envío.

Combinan seguimiento, perfil y motor, como hacía la UI de Streamlit, pero sin depender de ella. La IA
llega siempre desde quien llama (en la API, medida contra el cupo de la cuenta).

El análisis guarda el mapa de evidencias de la IA: el match se recalcula sin IA cada vez que se
consulta, y solo se vuelve a llamar a la IA cuando el perfil cambió y la persona pide actualizar.
"""

import json
from dataclasses import dataclass

from core.capture import canonical_url, capture_vacancy
from core.engine import pipeline
from core.engine.cover import CoverNote, write_cover_note
from core.engine.document import CVDocument, render
from core.engine.screening import ScreeningAnswer, answer_screening
from core.errors import UserInputError
from core.llm.client import LLMClient
from core.profile import service as profiles
from core.profile.completion import Candidate, split_into_achievements
from core.profile.snapshot import ProfileSnapshot
from core.tracking import service as tracking
from core.tracking.models import Application
from core.vacancy import VacancyAnalysis
from models import UserProfile
from services.pdf_generator import build_pdf_filename


class DuplicateVacancyError(UserInputError):
    def __init__(self, application: Application):
        super().__init__("Ya tienes esta vacante")
        self.application_id = application.id


@dataclass
class Loaded:
    application: Application
    vacancy: VacancyAnalysis
    snapshot: ProfileSnapshot
    analysis: pipeline.Analysis | None  # None: nunca se calculó la compatibilidad
    stale: bool  # el perfil cambió desde que la IA buscó evidencias


def contact(username: str) -> UserProfile:
    user = profiles.get_user(username)
    return UserProfile(username=username, full_name=user.full_name, email=user.email, phone=user.phone,
                       linkedin_url=user.linkedin_url, github_url=user.github_url)


def _snapshot_with_experience(username: str) -> ProfileSnapshot:
    snapshot = profiles.snapshot(username)
    if not snapshot.experiences:
        raise UserInputError("Registra primero tu experiencia: sin ella no hay con qué comparar la vacante.")
    return snapshot


def _save(username: str, application_id: int, analysis: pipeline.Analysis, snapshot: ProfileSnapshot) -> None:
    tracking.set_match(
        username, application_id, analysis.match.score,
        json.dumps(pipeline.match_summary(analysis.match), ensure_ascii=False),
        pipeline.evidence_json(analysis.evidence, snapshot),
    )


# ── vacantes y análisis ───────────────────────────────────────────────


def add_vacancy(username: str, llm: LLMClient, *, text: str = "", url: str = "", prepare: bool = False) -> int:
    """Trae (si hay enlace), analiza y guarda la vacante: en la bandeja o, con `prepare`, lista para postular."""
    url, platform = canonical_url(url) if url.strip() else "", ""
    if url and (existing := tracking.find_by_url(username, url)) is not None:
        raise DuplicateVacancyError(existing)
    snapshot = _snapshot_with_experience(username)
    if url:
        captured = capture_vacancy(url)
        url, platform, text = canonical_url(captured.url), captured.platform, captured.text
        if (existing := tracking.find_by_url(username, url)) is not None:
            raise DuplicateVacancyError(existing)
    if not text.strip():
        raise UserInputError("Pega el texto de la vacante o su enlace.")
    result = pipeline.analyze(llm, snapshot, text=text)
    if url and (existing := tracking.find_by_url(username, url)) is not None:  # doble envío durante el análisis
        raise DuplicateVacancyError(existing)
    return tracking.create_application(
        username, role=result.vacancy.role, company=result.vacancy.company, platform=platform, url=url,
        vacancy_text=text, analysis_json=result.vacancy.model_dump_json(),
        match_json=json.dumps(pipeline.match_summary(result.match), ensure_ascii=False),
        evidence_json=pipeline.evidence_json(result.evidence, snapshot), match_score=result.match.score,
        status="guardada" if prepare else "por_revisar",
    )


def load(username: str, application_id: int) -> Loaded:
    """Análisis actual, sin IA: el match se recalcula con el mapa de evidencias guardado."""
    application = tracking.get_application(username, application_id)
    if not application.analysis_json:
        raise UserInputError("Esta postulación se registró sin el texto de la vacante: no hay qué analizar.")
    vacancy = VacancyAnalysis.model_validate_json(application.analysis_json)
    snapshot = profiles.snapshot(username)
    evidence, fingerprint = pipeline.load_evidence(application.evidence_json)
    if evidence is None:
        return Loaded(application, vacancy, snapshot, None, True)
    analysis = pipeline.rematch(vacancy, evidence, snapshot)
    return Loaded(application, vacancy, snapshot, analysis, fingerprint != pipeline.profile_fingerprint(snapshot))


def refresh(username: str, application_id: int, llm: LLMClient) -> Loaded:
    """Vuelve a pedir a la IA las evidencias con el perfil de hoy (tras agregar logros, p. ej.)."""
    loaded = load(username, application_id)
    snapshot = _snapshot_with_experience(username)
    analysis = pipeline.match_only(llm, snapshot, loaded.vacancy)
    _save(username, application_id, analysis, snapshot)
    return Loaded(tracking.get_application(username, application_id), loaded.vacancy, snapshot, analysis, False)


def ensure(username: str, application_id: int, llm: LLMClient) -> Loaded:
    """Análisis listo para usar; solo llama a la IA si nunca se calculó."""
    loaded = load(username, application_id)
    return loaded if loaded.analysis is not None else refresh(username, application_id, llm)


def prepare(username: str, application_id: int, llm: LLMClient) -> Loaded:
    """«Preparar postulación» desde la bandeja: match con el perfil de hoy y pasa a «Guardada»."""
    loaded = refresh(username, application_id, llm)
    if loaded.application.status in ("por_revisar", "descartada"):
        tracking.change_status(username, application_id, "guardada", "Elegida para postular")
    return load(username, application_id)


# ── CV ────────────────────────────────────────────────────────────────


def _store_cv(username: str, application_id: int, document: CVDocument, output, role: str, company: str) -> tuple[int, str]:
    filename = build_pdf_filename(contact(username), role, company)
    cv_id = tracking.attach_cv(
        username, application_id, pdf=output.pdf, docx=output.docx, markdown=document.to_markdown(),
        language=document.language, filename=filename, document_json=json.dumps(document.to_dict(), ensure_ascii=False),
    )
    return cv_id, filename


def generate_cv(username: str, application_id: int, *, write_llm: LLMClient, extract_llm: LLMClient, focus: str = "") -> dict:
    loaded = ensure(username, application_id, extract_llm)
    generated = pipeline.generate(write_llm, loaded.snapshot, contact(username), loaded.analysis, extra_focus=focus)
    cv_id, filename = _store_cv(username, application_id, generated.document, generated.output,
                                loaded.vacancy.role, loaded.vacancy.company)
    return {
        "cv_id": cv_id, "filename": filename, "pages": generated.output.pages, "trimmed": generated.output.trimmed,
        "reverted": [reason for reasons in generated.reverted.values() for reason in reasons],
        "summary_replaced": generated.summary_replaced,
    }


def edit_cv(username: str, cv_id: int, *, summary: str, bullets: list[list[tuple[str, bool]]]) -> dict:
    """Aplica ediciones (texto e inclusión de viñetas, resumen) y guarda una VERSIÓN NUEVA del CV.

    Los CV ya generados nunca se modifican: el que se envió debe seguir siendo exactamente ese.
    Lo editado a mano no se verifica (es responsabilidad de la persona, como en Streamlit).
    """
    record = tracking.get_cv(username, cv_id)
    if not record.document_json:
        raise UserInputError("Este CV se generó antes de que se pudiera editar. Genera uno nuevo.")
    document = CVDocument.from_dict(json.loads(record.document_json))
    if len(bullets) != len(document.experiences) or any(
        len(rows) != len(exp.bullets) for rows, exp in zip(bullets, document.experiences, strict=False)
    ):
        raise UserInputError("La edición no corresponde a este CV.")
    document.summary = summary.strip()
    for exp, rows in zip(document.experiences, bullets, strict=True):
        for bullet, (text, included) in zip(exp.bullets, rows, strict=True):
            bullet.text, bullet.included = text.strip(), included
    output = render(document, contact(username))  # puede recortar para caber en 1 página: se guarda lo recortado
    application = tracking.get_application(username, record.application_id)  # puede no tener análisis (Streamlit)
    new_id, filename = _store_cv(username, record.application_id, document, output, application.role, application.company)
    return {"cv_id": new_id, "filename": filename, "pages": output.pages, "trimmed": output.trimmed}


# ── ayudas para postular ──────────────────────────────────────────────


def screening(username: str, application_id: int, questions: list[str], llm: LLMClient) -> list[ScreeningAnswer]:
    loaded = load(username, application_id)
    return answer_screening(llm, questions, loaded.snapshot, loaded.vacancy)


def cover_note(username: str, application_id: int, *, write_llm: LLMClient, extract_llm: LLMClient) -> CoverNote:
    loaded = ensure(username, application_id, extract_llm)
    return write_cover_note(write_llm, loaded.vacancy, loaded.analysis.match, loaded.snapshot)


def gap_story(
    username: str, application_id: int, requirement: int, experience_id: int, story: str, llm: LLMClient
) -> tuple[int, list[Candidate]]:
    """«Sí lo he hecho»: lo que cuenta la persona sobre un requisito faltante se vuelve logros verificados.

    Devuelve (logros agregados, candidatos con su verificación). El análisis queda desactualizado
    hasta que la persona lo actualice.
    """
    if not story.strip():
        raise UserInputError("Cuéntanos cómo lo hacías.")
    loaded = load(username, application_id)
    if not 0 <= requirement < len(loaded.vacancy.requirements):
        raise UserInputError("Ese requisito no existe en la vacante.")
    experience = next((e for e in loaded.snapshot.experiences if e.id == experience_id), None)
    if experience is None:
        raise UserInputError("Ese empleo no está en tu perfil.")
    context = f"La vacante pide: {loaded.vacancy.requirements[requirement].text}"
    candidates = split_into_achievements(llm, experience, story, context=context)
    texts = [c.text for c in candidates if c.suggested]
    added = profiles.append_achievements(username, experience_id, texts) if texts else 0
    return added, candidates
