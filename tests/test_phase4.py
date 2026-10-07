import json

import pytest

from core.capture import CapturedVacancy, CaptureError, canonical_url
from core.discovery import missing_musts, parse_links, search_links, slug, suggest_titles, triage
from core.engine.cover import write_cover_note
from core.engine.pipeline import analyze, match_summary
from core.llm.client import LLMAuthError
from core.profile import service as profiles
from core.tracking import service as tracking
from tests.test_core_engine import _EVIDENCE, _VACANCY, FakeLLM, _match, _profile
from ui.text import md

JOB = "https://www.linkedin.com/jobs/view/4012345678"


class TestUrls:
    @pytest.mark.parametrize("url", [
        "https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=aux",
        "https://co.linkedin.com/jobs/view/auxiliar-administrativa-at-nissan-4012345678?trk=public_jobs",
        "https://www.linkedin.com/jobs/view/4012345678/",
        "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4012345678",
    ])
    def test_linkedin_variants_are_the_same_vacancy(self, url):
        assert canonical_url(url) == JOB
        assert tracking.normalize_url(url) == "linkedin.com/jobs/view/4012345678"

    def test_other_urls_keep_their_path(self):
        url = "https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-aux-ABC123"
        assert canonical_url(url + "?utm=x") == url + "?utm=x"
        assert tracking.normalize_url(url + "/?utm_source=x&trk=y") == "co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-aux-ABC123"
        assert canonical_url("https://www.linkedin.com/feed/") == "https://www.linkedin.com/feed/"
        assert tracking.normalize_url("no es un enlace") == ""

    def test_query_params_that_identify_the_vacancy_are_kept(self):
        a, b = "https://co.indeed.com/viewjob?jk=aaa", "https://co.indeed.com/viewjob?jk=bbb&utm_source=mail"
        assert tracking.normalize_url(a) != tracking.normalize_url(b)
        assert tracking.normalize_url("https://co.indeed.com/viewjob?utm_medium=x&jk=bbb") == "co.indeed.com/viewjob?jk=bbb"
        assert tracking.normalize_url("https://empresa.com/career?job=2&lang=es") == tracking.normalize_url(
            "https://empresa.com/career?lang=es&job=2&fbclid=z")

    def test_parse_links_dedupes_and_strips_punctuation(self):
        text = (f"mira esta: {JOB}?trk=x, y esta (https://www.elempleo.com/co/ofertas-trabajo/aux-123).\n"
                "https://www.linkedin.com/jobs/search/?currentJobId=4012345678\nhttps://www.elempleo.com/co/ofertas-trabajo/aux-123")
        assert parse_links(text) == [JOB, "https://www.elempleo.com/co/ofertas-trabajo/aux-123"]
        assert parse_links("sin enlaces") == []

    def test_search_links(self):
        assert slug("Técnico en Logística / Bodega") == "tecnico-en-logistica-bodega"
        links = dict(search_links("Auxiliar Administrativa", "Bogotá"))
        assert links["Computrabajo"] == "https://co.computrabajo.com/trabajo-de-auxiliar-administrativa-en-bogota"
        assert links["elempleo"] == "https://www.elempleo.com/co/ofertas-empleo/bogota/auxiliar-administrativa"
        assert links["Magneto"] == "https://www.magneto365.com/co/trabajos/buscar?q=Auxiliar%20Administrativa"
        assert links["LinkedIn"].endswith("keywords=Auxiliar%20Administrativa&location=Bogot%C3%A1%2C%20Colombia")
        assert dict(search_links("Cajera"))["Computrabajo"].endswith("trabajo-de-cajera")
        assert search_links("  ") == []


def test_suggest_titles_puts_real_roles_first_and_dedupes():
    llm = FakeLLM({"titles": ["asistente administrativa", "Auxiliar de Facturación", "Auxiliar de Cartera"]})
    titles = suggest_titles(llm, _profile())
    assert titles == ["Asistente Administrativa", "Auxiliar Administrativa", "Cajera", "Auxiliar de Facturación", "Auxiliar de Cartera"]
    assert "180 facturas" in llm.prompts[0]


def test_md_escapes_links_images_and_directives():
    assert md("[clic](http://x) ![](http://t/p.png) :red[hola] **b**") == (
        "\\[clic\\]\\(http\\://x\\) \\!\\[\\]\\(http\\://t/p.png\\) \\:red\\[hola\\] \\*\\*b\\*\\*")


def test_match_summary_and_missing_musts():
    evidence = json.loads(json.dumps(_EVIDENCE))
    evidence["items"][2] = {"requirement": 3, "level": "no", "evidence": []}
    analysis = analyze(FakeLLM(_VACANCY, evidence), _profile(), text="vacante")
    summary = match_summary(analysis.match)
    assert summary["score"] == analysis.match.score and summary["required_years"] == 2
    assert missing_musts(json.dumps(summary)) == ["Excel intermedio"]
    assert missing_musts("") == [] and missing_musts("{roto") == []


class TestTriage:
    @pytest.fixture(autouse=True)
    def _db(self, monkeypatch):
        monkeypatch.setattr(profiles, "_ready", False)
        profiles.ensure_ready()
        profiles.create_user("ana")
        profiles.create_user("eve")

    @staticmethod
    def _capture(url):
        if "login" in url:
            raise CaptureError("El sitio respondió 403")
        final = JOB if "/r/" in url else url  # simula un acortador que redirige a LinkedIn
        return CapturedVacancy(final, "LinkedIn", "Auxiliar Administrativo en Logística Andina...", "jobposting", "Aux", "LA")

    def test_adds_to_inbox_skips_repeated_and_reports_errors(self):
        urls = [JOB + "?trk=a", "https://empresa.com/login/oferta", JOB.replace("4012345678", "999999999")]
        llm = FakeLLM(_VACANCY, _EVIDENCE, {"is_vacancy": False})
        results = list(triage("ana", urls, llm, _profile(), capture=self._capture))
        assert [r.status for r in results] == ["agregada", "error", "error"]
        assert "403" in results[1].message and "no parece" in results[2].message

        app = tracking.get_application("ana", results[0].application_id)
        assert (app.status, app.url, app.platform) == ("por_revisar", JOB, "LinkedIn")
        assert json.loads(app.match_json)["score"] == app.match_score == results[0].score
        assert json.loads(app.analysis_json)["role"] == "Auxiliar Administrativo"

        again = list(triage("ana", ["https://www.linkedin.com/jobs/search/?currentJobId=4012345678"], FakeLLM(), _profile(),
                            capture=self._capture))
        assert again[0].status == "repetida" and again[0].application_id == app.id and "por revisar" in again[0].message
        # Cada perfil tiene su propia bandeja
        assert list(triage("eve", [JOB], FakeLLM(_VACANCY, _EVIDENCE), _profile(), capture=self._capture))[0].status == "agregada"

    def test_short_link_first_then_long_link_is_repeated(self):
        list(triage("ana", ["https://lnkd.example/r/4012345678"], FakeLLM(_VACANCY, _EVIDENCE), _profile(), capture=self._capture))
        assert tracking.list_applications("ana")[0].url == JOB  # se guarda la URL final, no la corta
        assert list(triage("ana", [JOB], FakeLLM(), _profile(), capture=self._capture))[0].status == "repetida"

    def test_unexpected_error_only_skips_that_link(self):
        def capture(url):
            if "boom" in url:
                raise LookupError("codificación rara")
            return self._capture(url)

        results = list(triage("ana", ["https://empresa.com/boom", JOB], FakeLLM(_VACANCY, _EVIDENCE), _profile(), capture=capture))
        assert [r.status for r in results] == ["error", "agregada"] and "inesperado" in results[0].message

    def test_same_vacancy_after_redirect_is_repeated(self):
        list(triage("ana", [JOB], FakeLLM(_VACANCY, _EVIDENCE), _profile(), capture=self._capture))
        results = list(triage("ana", ["https://lnkd.example/r/4012345678"], FakeLLM(), _profile(), capture=self._capture))
        assert results[0].status == "repetida"

    def test_invalid_key_stops_the_batch(self):
        class AuthFail(FakeLLM):
            def complete(self, prompt, **kwargs):
                raise LLMAuthError("clave inválida")

        with pytest.raises(LLMAuthError):
            list(triage("ana", [JOB, JOB + "1"], AuthFail(), _profile(), capture=self._capture))
        assert tracking.count("ana", ("por_revisar",)) == 0

    def test_timeouts_skip_only_that_vacancy(self):
        class Slow(FakeLLM):
            def complete(self, prompt, **kwargs):
                if not self.responses:
                    raise RuntimeError("Gemini tardó demasiado en responder.")
                return super().complete(prompt, **kwargs)

        results = list(triage("ana", [JOB, JOB.replace("4012345678", "5012345678")], Slow(_VACANCY, _EVIDENCE), _profile(),
                              capture=self._capture))
        assert [r.status for r in results] == ["agregada", "error"]

    def test_inbox_is_not_counted_as_applications(self):
        triaged = tracking.create_application("ana", role="A", status="por_revisar", url=JOB)
        discarded = tracking.create_application("ana", role="B", status="descartada")
        tracking.create_application("ana", role="C", status="guardada")
        s = tracking.summary("ana")
        assert s.total == 1 and tracking.count("ana", ("por_revisar",)) == 1
        sent = tracking.create_application("ana", role="D", status="postulada", applied_on=tracking.today())
        tracking.change_status("ana", sent, "descartada")  # enviada y luego descartada: sigue contando
        assert tracking.summary("ana").total == 2
        tracking.set_match("ana", triaged, 77, '{"score": 77}')
        assert tracking.get_application("ana", triaged).match_score == 77
        assert tracking.find_by_url("eve", JOB) is None and tracking.find_by_url("ana", JOB).id == triaged
        cv_id = tracking.attach_cv("ana", triaged, pdf=b"%PDF", docx=b"PK", markdown="", language="es", filename="cv.pdf")
        assert cv_id and tracking.get_application("ana", triaged).status == "cv_generado"
        assert tracking.get_application("ana", discarded).status == "descartada"


class TestCoverNote:
    def test_verified_note_is_kept(self):
        vacancy, match = _match()
        text = ("Hola, me postulo a la vacante de Auxiliar Administrativo en Logística Andina. "
                "Elaboré la facturación de 180 facturas al mes y concilié cuentas por cobrar con cartera. Adjunto mi CV.")
        llm = FakeLLM({"text": text})
        note = write_cover_note(llm, vacancy, match, _profile())
        assert note.text == text and not note.fallback
        assert "PROHIBIDO inventar" in llm.prompts[0] and "180 facturas" in llm.prompts[0]

    def test_invented_data_falls_back_to_real_data(self):
        vacancy, match = _match()
        note = write_cover_note(FakeLLM({"text": "Reduje la cartera un 45% con SAP en Bancolombia."}), vacancy, match, _profile())
        assert note.fallback and note.problems
        assert "45" not in note.text and "SAP" not in note.text
        assert note.text.startswith("Hola, me postulo a la vacante de Auxiliar Administrativo en Logística Andina")
        assert f"{int(match.experience_years)} años" in note.text
