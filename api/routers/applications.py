"""Postulaciones: lista por vista, detalle con historial y CVs, estados, notas, recordatorios y envío."""

import json
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response, status

from api.auth import CurrentAccount
from api.schemas import (
    ApplicationIn,
    ApplicationOut,
    ApplicationSummaryOut,
    CVOut,
    DetailsIn,
    EventOut,
    FollowUpIn,
    NoteIn,
    SentIn,
    StatusIn,
    SummaryOut,
)
from core.discovery import missing_musts
from core.tracking import service as tracking
from core.tracking.models import (
    ACTIVE_STATUSES,
    APPLIED_STATUSES,
    STATUSES,
    TRIAGE_STATUSES,
    Application,
)

router = APIRouter(tags=["postulaciones"])

_CLOSED = tuple(s for s in STATUSES if s not in ACTIVE_STATUSES and s not in TRIAGE_STATUSES)
_VIEWS = {
    "activas": ACTIVE_STATUSES,
    "cerradas": _CLOSED,
    "todas": ACTIVE_STATUSES + _CLOSED,
    "bandeja": TRIAGE_STATUSES,
    "descartadas": ("descartada",),
}
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _summary(a: Application) -> ApplicationSummaryOut:
    return ApplicationSummaryOut(
        id=a.id, role=a.role, company=a.company, platform=a.platform, url=a.url, status=a.status,
        status_label=STATUSES.get(a.status, (a.status, ""))[0], match_score=a.match_score, applied_on=a.applied_on,
        next_action_on=a.next_action_on, next_action=a.next_action, created_at=a.created_at, updated_at=a.updated_at,
        missing_musts=missing_musts(a.match_json), partial_musts=missing_musts(a.match_json, "parcial"),
    )


def _json(text: str) -> dict | None:
    try:
        value = json.loads(text) if text else None
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _detail(username: str, application_id: int) -> ApplicationOut:
    a = tracking.get_application(username, application_id)
    return ApplicationOut(
        **_summary(a).model_dump(), contact=a.contact, vacancy_text=a.vacancy_text,
        vacancy=_json(a.analysis_json), match=_json(a.match_json),
        events=[EventOut(id=e.id, kind=e.kind, from_status=e.from_status, to_status=e.to_status, detail=e.detail,
                         created_at=e.created_at) for e in a.events],
        cvs=[CVOut(id=c.id, language=c.language, filename=c.filename, pdf_sha256=c.pdf_sha256, sent_at=c.sent_at,
                   created_at=c.created_at, intact=tracking.verify_cv(c)) for c in a.cvs],
    )


@router.get("/applications", response_model=list[ApplicationSummaryOut])
def list_applications(
    account: CurrentAccount,
    view: Literal["activas", "cerradas", "todas", "bandeja", "descartadas"] = "activas",
) -> list[ApplicationSummaryOut]:
    applications = tracking.list_applications(account.username, _VIEWS[view], with_files=False)
    if view in ("cerradas", "todas"):  # lo descartado sin enviar vive en la bandeja
        applications = [a for a in applications if not (a.status == "descartada" and a.applied_on is None)]
    if view == "bandeja":
        applications.sort(key=lambda a: (a.match_score if a.match_score is not None else -1, a.id), reverse=True)
    return [_summary(a) for a in applications]


@router.get("/applications/summary", response_model=SummaryOut)
def summary(account: CurrentAccount) -> SummaryOut:
    s = tracking.summary(account.username)
    return SummaryOut(total=s.total, sent=s.sent, responses=s.responses, response_rate=s.response_rate,
                      by_status=s.by_status, due=[_summary(a) for a in s.due])


@router.post("/applications", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(body: ApplicationIn, account: CurrentAccount) -> ApplicationOut:
    applied_on = (body.applied_on or tracking.today()) if body.status in APPLIED_STATUSES else None
    application_id = tracking.create_application(
        account.username, role=body.role, company=body.company, platform=body.platform, url=body.url,
        status=body.status, applied_on=applied_on,
    )
    return _detail(account.username, application_id)


@router.get("/applications/{application_id}", response_model=ApplicationOut)
def get_application(application_id: int, account: CurrentAccount) -> ApplicationOut:
    return _detail(account.username, application_id)


@router.patch("/applications/{application_id}", response_model=ApplicationOut)
def update_details(application_id: int, body: DetailsIn, account: CurrentAccount) -> ApplicationOut:
    tracking.update_details(account.username, application_id, **body.model_dump(exclude_none=True))
    return _detail(account.username, application_id)


@router.post("/applications/{application_id}/status", response_model=ApplicationOut)
def change_status(application_id: int, body: StatusIn, account: CurrentAccount) -> ApplicationOut:
    tracking.change_status(account.username, application_id, body.status, body.note)
    return _detail(account.username, application_id)


@router.post("/applications/{application_id}/notes", response_model=ApplicationOut)
def add_note(application_id: int, body: NoteIn, account: CurrentAccount) -> ApplicationOut:
    tracking.add_note(account.username, application_id, body.note)
    return _detail(account.username, application_id)


@router.put("/applications/{application_id}/follow-up", response_model=ApplicationOut)
def set_follow_up(application_id: int, body: FollowUpIn, account: CurrentAccount) -> ApplicationOut:
    tracking.set_follow_up(account.username, application_id, body.on, body.what)
    return _detail(account.username, application_id)


@router.post("/applications/{application_id}/sent", response_model=ApplicationOut)
def mark_sent(application_id: int, body: SentIn, account: CurrentAccount) -> ApplicationOut:
    tracking.mark_sent(account.username, application_id, body.cv_id, sent_on=body.sent_on, platform=body.platform)
    return _detail(account.username, application_id)


@router.delete("/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(application_id: int, account: CurrentAccount) -> Response:
    tracking.delete_application(account.username, application_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/cvs/{cv_id}/{fmt}", response_class=Response, responses={200: {"content": {"application/pdf": {}, _DOCX: {}}}})
def download_cv(cv_id: int, fmt: Literal["pdf", "docx"], account: CurrentAccount) -> Response:
    """El archivo exacto que se guardó; si no coincide con su huella, no se entrega."""
    record = tracking.get_cv(account.username, cv_id)
    if not tracking.verify_cv(record):
        raise HTTPException(status.HTTP_409_CONFLICT, "El archivo no coincide con su huella y no se entrega")
    data, media, digest = (
        (record.pdf, "application/pdf", record.pdf_sha256) if fmt == "pdf" else (record.docx, _DOCX, record.docx_sha256)
    )
    filename = record.filename.rsplit(".", 1)[0] + f".{fmt}"
    return Response(data, media_type=media, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "X-Content-SHA256": digest,
    })
