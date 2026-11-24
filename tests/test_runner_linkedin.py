"""El recorredor de «Solicitud sencilla» contra una copia local del formulario (sin LinkedIn ni red).

Necesita Playwright y un Chromium; si no están (p. ej. en la CI), se salta.
"""

from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from runner import linkedin  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "easy_apply.html"


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Sin Chromium para Playwright: {e}")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


@pytest.fixture
def cv(tmp_path):
    path = tmp_path / "Camilo_Maestre_Backend_Empresa.pdf"
    path.write_bytes(b"%PDF-1.4 prueba")
    return path


def answerer(questions):
    known = {"¿Cuántos años de experiencia tienes con Python?": "2", "¿Cuál es tu nivel de inglés?*": "A2",
             "¿Puedes hacer práctica empresarial?*": "Sí", "¿Tienes experiencia en desarrollo backend?": "Sí",
             "¿Cuántos años de experiencia tienes con Java?": "1"}
    return {q.label: known[q.label] for q in questions if q.label in known}


def test_dry_run_reaches_review_and_never_sends(page, cv, tmp_path):
    result = linkedin.apply(page, FIXTURE.as_uri(), cv, answerer, submit=False, shots=tmp_path)
    assert result.status == "revisada", result
    assert page.evaluate("window.sent") is False
    assert page.evaluate("window.discarded") is True and not page.evaluate("window.saved")  # descartada, no guardada
    assert Path(result.screenshot).is_file()


def test_auto_fills_uploads_unfollows_and_sends(page, cv):
    result = linkedin.apply(page, FIXTURE.as_uri(), cv, answerer, submit=True)
    assert result.status == "enviada", result
    sent = page.evaluate("window.answers")
    assert sent["py"] == "2" and sent["en"] == "A2" and sent["si"] is True and sent["tel"] == "3000000000"
    assert sent["be1"] is True and sent["be2"] is False  # radios de 2026-11: «Sí» → «Yes»
    assert sent["java"] == "1"  # los años que LinkedIn traía guardados («3») se responden de nuevo
    assert page.evaluate("window.follow") is False  # «Seguir a la empresa» desmarcado
    assert page.evaluate("window.cvName") == cv.name  # se subió el CV de esta vacante


def test_unanswered_required_question_skips_without_sending(page, cv):
    result = linkedin.apply(page, FIXTURE.as_uri(), cv, lambda qs: {}, submit=True)
    assert result.status == "saltada"
    assert "¿Cuántos años de experiencia tienes con Python?" in result.unanswered
    assert page.evaluate("window.sent") is False


def test_never_sends_with_a_cv_that_is_not_this_vacancys(page, cv, monkeypatch):
    monkeypatch.setattr(linkedin, "_upload", lambda page, dialog, cv_pdf: True)  # la subida «no ocurre»
    result = linkedin.apply(page, FIXTURE.as_uri(), cv, answerer, submit=True)
    assert result.status == "saltada" and "CV" in result.detail
    assert page.evaluate("window.sent") is False


def test_selects_the_uploaded_cv_when_linkedin_keeps_the_old_one(page, cv):
    page.add_init_script("window.keepOld = true")  # LinkedIn deja elegido el CV viejo
    result = linkedin.apply(page, FIXTURE.as_uri(), cv, answerer, submit=True)
    assert result.status == "enviada", result
    assert page.evaluate("window.answers")["new"] is True


def test_counts_as_sent_when_the_job_shows_applied_without_the_notice(page, cv):
    page.add_init_script("window.quietSend = true")
    result = linkedin.apply(page, FIXTURE.as_uri(), cv, answerer, submit=True)
    assert result.status == "enviada", result
    assert page.evaluate("window.sent") is True


def test_a_job_description_that_mentions_a_limit_is_not_linkedins_notice(page):
    # Caso real: la descripción de una oferta frenó LinkedIn dos días («reached the …» … «limit»).
    description = ("<p>We have reached the point where our pharmacy serves millions of customers across Europe, and our "
                   "growth has no limit: join a team that builds the platform for the next decade of e-commerce. </p>" * 3)
    page.set_content(f"<main><h1>Data Analyst</h1><section>{description}</section></main>")
    assert linkedin._limit_notice(page) == ""
    page.set_content("<main><div role='alert'>Has alcanzado el límite diario de solicitudes de Solicitud sencilla.</div></main>")
    assert "límite diario" in linkedin._limit_notice(page)


def test_reads_the_2026_radio_questions(page):
    page.goto(FIXTURE.as_uri())
    page.evaluate("current = 2; document.getElementById('dlg').hidden = false; render()")
    questions = {q.label: q for q in linkedin._questions(page.get_by_role("dialog").first)}
    backend = questions["¿Tienes experiencia en desarrollo backend?"]
    assert backend.kind == "radio" and backend.required and backend.options == ["Yes", "No"]


def test_a_closed_job_is_skipped_not_handed_over(page, cv):
    page.route("https://example.com/job", lambda route: route.fulfill(content_type="text/html; charset=utf-8",
                                                                       body="<h1>Analista</h1><p>Ya no se aceptan solicitudes</p>"))
    result = linkedin.apply(page, "https://example.com/job", cv, answerer, submit=True)
    assert result.status == "saltada" and "ya no recibe" in result.detail


def test_the_2026_applied_notice_means_already_applied(page, cv):
    page.route("https://example.com/job", lambda route: route.fulfill(content_type="text/html; charset=utf-8",
                                                                       body="<h1>Analista</h1><p>Solicitud enviada justo ahora</p>"))
    assert linkedin.apply(page, "https://example.com/job", cv, answerer, submit=True).status == "ya_postulada"


def test_saved_years_stay_when_there_is_no_new_answer(page, cv):
    known = {"¿Cuántos años de experiencia tienes con Python?": "2", "¿Cuál es tu nivel de inglés?*": "A2",
             "¿Puedes hacer práctica empresarial?*": "Sí", "¿Tienes experiencia en desarrollo backend?": "Sí"}
    result = linkedin.apply(page, FIXTURE.as_uri(), cv, lambda qs: {q.label: known[q.label] for q in qs if q.label in known},
                            submit=True)
    assert result.status == "enviada" and page.evaluate("window.answers")["java"] == "3"
