from datetime import date, timedelta

import pytest

from core.profile import service as profiles
from core.profile.repository import NotFoundError
from core.tracking import service as tracking


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(profiles, "_ready", False)
    profiles.ensure_ready()
    profiles.create_user("ana")
    profiles.create_user("eve")


def _app(**kw):
    return tracking.create_application("ana", role="Auxiliar Administrativa", company="Logística Andina", **kw)


def _attach(app_id, payload=b"%PDF-1"):
    return tracking.attach_cv("ana", app_id, pdf=payload, docx=b"PK-docx", markdown="## CV", language="es", filename="cv.pdf")


def test_full_lifecycle_is_traced():
    app_id = _app(platform="Computrabajo", match_score=88)
    cv_id = _attach(app_id)
    tracking.mark_sent("ana", app_id, cv_id, sent_on=date(2026, 10, 1))
    tracking.change_status("ana", app_id, "entrevista", "Me llamaron el lunes")
    tracking.add_note("ana", app_id, "Entrevista el jueves 10 am")
    app = tracking.get_application("ana", app_id)
    assert app.status == "entrevista" and app.applied_on == date(2026, 10, 1)
    assert [e.kind for e in app.events] == ["creada", "cv_generado", "estado", "cv_enviado", "estado", "estado", "nota"]
    assert [(e.from_status, e.to_status) for e in app.events if e.kind == "estado"] == [
        ("guardada", "cv_generado"), ("cv_generado", "postulada"), ("postulada", "entrevista")]
    sent = next(e for e in app.events if e.kind == "cv_enviado")
    assert app.cvs[0].pdf_sha256[:12] in sent.detail and app.cvs[0].sent_at is not None


def test_only_a_cv_generated_for_this_vacancy_can_be_sent():
    first, second = _app(), _app()
    cv_for_first = _attach(first)
    with pytest.raises(NotFoundError):
        tracking.mark_sent("ana", second, cv_for_first)
    assert tracking.get_application("ana", second).status == "guardada"


def test_cv_integrity_check():
    app_id = _app()
    _attach(app_id, b"%PDF-original")
    record = tracking.get_application("ana", app_id).cvs[0]
    assert tracking.verify_cv(record)
    record.pdf = b"%PDF-alterado"
    assert not tracking.verify_cv(record)


def test_follow_up_defaults_and_due_list():
    app_id = _app()
    tracking.mark_sent("ana", app_id, None, sent_on=date(2026, 10, 1), platform="LinkedIn")
    app = tracking.get_application("ana", app_id)
    assert app.next_action_on == date(2026, 10, 1) + timedelta(days=7) and app.platform == "LinkedIn"
    assert [a.id for a in tracking.summary("ana", on=date(2026, 10, 8)).due] == [app_id]
    assert tracking.summary("ana", on=date(2026, 10, 7)).due == []
    tracking.change_status("ana", app_id, "rechazada")  # cerrada: sin recordatorio
    assert tracking.get_application("ana", app_id).next_action_on is None


def test_summary_counts_and_response_rate():
    a, b, _ = _app(), _app(), _app()
    for app_id in (a, b):
        tracking.mark_sent("ana", app_id, None)
    tracking.change_status("ana", b, "entrevista")
    s = tracking.summary("ana")
    assert s.total == 3 and s.by_status["guardada"] == 1 and s.sent == 2 and s.response_rate == 0.5


def test_ownership_everywhere():
    app_id = _app()
    for action in (
        lambda: tracking.get_application("eve", app_id),
        lambda: tracking.change_status("eve", app_id, "oferta"),
        lambda: tracking.add_note("eve", app_id, "x"),
        lambda: tracking.mark_sent("eve", app_id, None),
        lambda: tracking.delete_application("eve", app_id),
    ):
        with pytest.raises(NotFoundError):
            action()
    assert tracking.list_applications("eve") == []


def test_unknown_status_and_details_update():
    app_id = _app()
    with pytest.raises(ValueError):
        tracking.change_status("ana", app_id, "contratada?")
    tracking.update_details("ana", app_id, contact="Laura (RRHH) laura@empresa.com", url="https://x.co/1")
    app = tracking.get_application("ana", app_id)
    assert app.contact.startswith("Laura") and app.events[-1].kind == "datos"


def test_deleting_user_or_application_cascades():
    app_id = _app()
    _attach(app_id)
    tracking.delete_application("ana", app_id)
    assert tracking.list_applications("ana") == []
    other = _app()
    _attach(other)
    profiles.delete_user("ana")
    from sqlalchemy import text

    from core.db import session_scope

    with session_scope() as s:
        assert s.execute(text("SELECT COUNT(*) FROM cv_documents")).scalar() == 0
