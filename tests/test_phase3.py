import json
from unittest.mock import MagicMock, patch

import pytest

from core.capture import CaptureError, capture_vacancy, detect_platform, html_to_text
from core.engine.screening import answer_screening
from core.profile.periods import parse_period
from core.profile.snapshot import AchievementSnap, ExperienceSnap, ProfileSnapshot, SkillSnap
from core.tracking.insights import build_insights
from core.tracking.models import Application

PUBLIC = [(2, 1, 6, "", ("93.184.216.34", 443))]
PRIVATE = [(2, 1, 6, "", ("10.0.0.5", 80))]

JOBPOSTING_HTML = """<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [{"@type": "BreadcrumbList"}, {"@type": "JobPosting",
 "title": "Auxiliar Administrativo", "hiringOrganization": {"name": "ACME"},
 "jobLocation": {"address": {"addressLocality": ["Barranquilla"], "addressCountry": "CO"}},
 "baseSalary": {"currency": "COP", "value": {"minValue": 1800000, "maxValue": 2200000, "unitText": "MONTH"}},
 "description": "<p>Facturación y <b>cartera</b>.</p><ul><li>Excel</li></ul>", "skills": ["Excel", "SAP"]}]}
</script></head><body>menú</body></html>"""


def _response(status=200, body="", location=None):
    r = MagicMock(status_code=status, encoding="utf-8")
    r.is_redirect = location is not None
    r.headers = {"Location": location} if location else {}
    r.iter_content.return_value = [body.encode()]
    return r


class TestCapture:
    def test_detect_platform(self):
        assert detect_platform("https://co.linkedin.com/jobs/view/1") == "LinkedIn"
        assert detect_platform("https://co.computrabajo.com/ofertas") == "Computrabajo"
        assert detect_platform("https://www.magneto365.com/co/empleos/x") == "Magneto"
        assert detect_platform("https://empresa.com/trabaja") == "Página de la empresa"
        assert detect_platform("https://linkedin.com.evil.co/x") == "Página de la empresa"

    @patch("core.capture.socket.getaddrinfo", return_value=PUBLIC)
    @patch("core.capture.requests.get")
    def test_jobposting_is_preferred(self, get, _dns):
        get.return_value = _response(body=JOBPOSTING_HTML)
        captured = capture_vacancy("https://www.elempleo.com/co/ofertas-trabajo/1")
        assert (captured.source, captured.platform, captured.title, captured.company) == ("jobposting", "elempleo", "Auxiliar Administrativo", "ACME")
        assert "Barranquilla" in captured.text and "1800000-2200000 COP" in captured.text and "cartera" in captured.text
        assert "<b>" not in captured.text and "Habilidades: Excel, SAP" in captured.text

    @patch("core.capture.socket.getaddrinfo", return_value=PUBLIC)
    @patch("core.capture.requests.get")
    def test_posting_dates(self, get, _dns):
        from datetime import date

        from core.capture import posting_dates

        today = date(2026, 10, 8)
        assert posting_dates({"datePosted": "2026-9-3", "validThrough": "2026-10-28T23:59:00Z"}, today=today) == \
            (date(2026, 9, 3), date(2026, 10, 28))  # elempleo escribe el mes sin cero
        assert posting_dates({"datePosted": "2027-01-01"}, today=today) == (None, None)  # publicada "en el futuro"
        assert posting_dates({"datePosted": "2026-09-01", "validThrough": "2026-08-01"}, today=today) == (date(2026, 9, 1), None)
        assert posting_dates({"datePosted": "ayer", "validThrough": "2026-02-30"}, today=today) == (None, None)
        get.return_value = _response(body=JOBPOSTING_HTML.replace('"title"', '"datePosted": "2026-10-01", "title"'))
        assert capture_vacancy("https://www.elempleo.com/co/ofertas-trabajo/1").posted_on == date(2026, 10, 1)

    @patch("core.capture.socket.getaddrinfo", return_value=PUBLIC)
    @patch("core.capture.requests.get")
    def test_falls_back_to_main_text(self, get, _dns):
        body = "<html><body><nav>menú</nav><main><h1>Auxiliar</h1><p>" + "Requisitos de la oferta. " * 20 + "</p><script>x=1</script></main></body></html>"
        get.return_value = _response(body=body)
        captured = capture_vacancy("https://co.computrabajo.com/ofertas-de-trabajo/x")
        assert captured.source == "page" and captured.text.startswith("Auxiliar") and "menú" not in captured.text and "x=1" not in captured.text

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x.com/", "javascript:alert(1)"])
    def test_rejects_other_schemes(self, url):
        with pytest.raises(CaptureError):
            capture_vacancy(url)

    @patch("core.capture.socket.getaddrinfo", return_value=PRIVATE)
    @patch("core.capture.requests.get")
    def test_rejects_private_destinations(self, get, _dns):
        with pytest.raises(CaptureError, match="interna"):
            capture_vacancy("http://intranet.empresa/")
        get.assert_not_called()

    @patch("core.capture.socket.getaddrinfo", side_effect=[PUBLIC, PRIVATE])
    @patch("core.capture.requests.get")
    def test_redirect_to_private_is_blocked(self, get, _dns):
        get.return_value = _response(status=302, location="http://169.254.169.254/latest/meta-data/")
        with pytest.raises(CaptureError, match="interna"):
            capture_vacancy("https://acortador.com/abc")
        assert get.call_count == 1

    @patch("core.capture.socket.getaddrinfo", return_value=PUBLIC)
    @patch("core.capture.requests.get")
    def test_login_walls_and_huge_pages(self, get, _dns):
        get.return_value = _response(status=999)
        with pytest.raises(CaptureError, match="999"):
            capture_vacancy("https://www.linkedin.com/jobs/view/1")
        huge = _response(body="")
        huge.iter_content.return_value = [b"x" * 1_000_000] * 4
        get.return_value = huge
        with pytest.raises(CaptureError, match="grande"):
            capture_vacancy("https://x.com/oferta")

    def test_html_to_text(self):
        assert html_to_text("<p>Hola &amp; <b>chao</b></p><script>malo()</script>") == "Hola & chao"


def _app(platform, status, score, keywords):
    return Application(platform=platform, status=status, match_score=score, role="x", company="y",
                       analysis_json=json.dumps({"is_vacancy": True, "role": "x", "keywords": keywords, "area": "Administrativa"}))


class TestInsights:
    PROFILE = ProfileSnapshot("ana", skills=(SkillSnap(1, "Excel", "Herramientas y software"),),
                              experiences=(ExperienceSnap(1, "Aux", "A", "", parse_period(""), "", "",
                                                          (AchievementSnap(1, "Manejé la facturación"),)),))

    def test_keywords_platforms_and_buckets(self):
        apps = [
            _app("Computrabajo", "entrevista", 85, ["Excel", "SAP", "facturación"]),
            _app("Computrabajo", "rechazada", 40, ["excel", "SAP"]),
            _app("LinkedIn", "postulada", 80, ["Excel"]),
            _app("LinkedIn", "guardada", None, ["Power BI"]),
            Application(platform="Magneto", status="postulada", role="m", company="", analysis_json=""),
        ]
        ins = build_insights(apps, self.PROFILE)
        assert (ins.applications, ins.analyzed, ins.sent) == (5, 4, 4)
        top = {k.keyword: (k.vacancies, k.owned) for k in ins.keywords}
        assert top["Excel"] == (3, True) and top["SAP"] == (2, False) and top["facturación"] == (1, True)
        assert [k.keyword for k in ins.top_gaps] == ["SAP", "Power BI"]
        computrabajo = next(p for p in ins.platforms if p.platform == "Computrabajo")
        assert (computrabajo.sent, computrabajo.progressed, computrabajo.rejected, computrabajo.progress_rate) == (2, 1, 1, 0.5)
        assert {label: (sent, prog) for label, sent, prog in ins.score_buckets} == {
            "Menos de 50": (1, 0), "50 a 74": (0, 0), "75 o más": (2, 1)}
        assert not ins.enough_data

    def test_platform_filter(self):
        apps = [_app("Computrabajo", "postulada", 70, ["Excel"]), _app("LinkedIn", "postulada", 70, ["SAP"])]
        ins = build_insights(apps, self.PROFILE, platform="LinkedIn")
        assert ins.applications == 1 and [k.keyword for k in ins.keywords] == ["SAP"]


class TestScreening:
    PROFILE = ProfileSnapshot("ana", experiences=(
        ExperienceSnap(1, "Auxiliar", "ACME", "Enero 2020 - Diciembre 2021", parse_period("Enero 2020 - Diciembre 2021"), "", "",
                       (AchievementSnap(1, "Elaboré 120 facturas al mes"),)),
    ))

    def _llm(self, payload):
        llm = MagicMock()
        llm.label = "fake:model"
        llm.complete.return_value = json.dumps(payload)
        return llm

    def test_answers_are_verified_and_padded(self):
        llm = self._llm({"answers": [
            {"question": "q1", "answer": "Tengo 2 años de experiencia en facturación"},
            {"question": "q2", "answer": "Sí, manejo SAP desde hace 5 años"},
        ]})
        answers = answer_screening(llm, ["¿Años en facturación?", "¿Maneja SAP?", "¿Aspiración salarial?"], self.PROFILE)
        assert answers[0].question == "¿Años en facturación?" and not answers[0].needs_you
        assert answers[1].needs_you and "SAP" in answers[1].note
        assert answers[2].needs_you and answers[2].answer == ""
        assert "24 meses" in llm.complete.call_args[0][0]

    def test_no_questions_no_call(self):
        llm = self._llm({})
        assert answer_screening(llm, ["  ", ""], self.PROFILE) == []
        llm.complete.assert_not_called()
