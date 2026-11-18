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
             "¿Puedes hacer práctica empresarial?*": "Sí"}
    return {q.label: known[q.label] for q in questions if q.label in known}


def test_dry_run_reaches_review_and_never_sends(page, cv, tmp_path):
    result = linkedin.apply(page, FIXTURE.as_uri(), cv, answerer, submit=False, shots=tmp_path)
    assert result.status == "revisada", result
    assert page.evaluate("window.sent") is False
    assert Path(result.screenshot).is_file()


def test_auto_fills_uploads_unfollows_and_sends(page, cv):
    result = linkedin.apply(page, FIXTURE.as_uri(), cv, answerer, submit=True)
    assert result.status == "enviada", result
    sent = page.evaluate("window.answers")
    assert sent["py"] == "2" and sent["en"] == "A2" and sent["si"] is True and sent["tel"] == "3000000000"
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
