from unittest.mock import MagicMock, patch

import pytest

from models import UserProfile
from services.pdf_generator import (
    build_html,
    build_pdf_filename,
    clean_markdown_output,
    generate_pdf,
    parse_vacancy_fields,
)


class TestCleanMarkdownOutput:
    def test_clean_triple_backtick_markdown(self):
        raw = "```markdown\n# CV\nContent\n```"
        assert clean_markdown_output(raw) == "# CV\nContent"

    def test_clean_triple_backtick_plain(self):
        raw = "```\n# CV\nContent\n```"
        assert clean_markdown_output(raw) == "# CV\nContent"

    def test_no_wrapper(self):
        raw = "# CV\nContent"
        assert clean_markdown_output(raw) == "# CV\nContent"

    def test_empty(self):
        assert clean_markdown_output("") == ""


class TestBuildHtml:
    def test_build_html_includes_profile_data(self):
        profile = UserProfile(
            username="test",
            full_name="John Doe",
            email="john@test.com",
            phone="+1 555",
            linkedin_url="https://linkedin.com/in/johndoe",
            github_url="https://github.com/johndoe",
        )
        cv_md = "## Perfil Profesional\nTest content."
        html = build_html(cv_md, profile)
        assert "JOHN DOE" in html
        assert "john@test.com" in html
        assert "+1 555" in html
        assert "linkedin.com/in/johndoe" in html
        assert "github.com/johndoe" in html
        assert "Test content" in html

    def test_build_html_empty_profile(self):
        profile = UserProfile(username="test")
        cv_md = "## Test\ncontent"
        html = build_html(cv_md, profile)
        assert "content" in html

    def test_build_html_neutralizes_raw_html_from_llm(self):
        profile = UserProfile(username="test")
        cv_md = '## Perfil\n<link rel="attachment" href="file:///etc/passwd">'
        html = build_html(cv_md, profile)
        assert "<link" not in html


class TestGeneratePdfSecurity:
    def test_pdf_does_not_embed_local_files(self, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("SECRETO_DE_PRUEBA")
        injection = f'"><link rel="attachment" href="file://{secret}"><a href="'
        profile = UserProfile(username="test", full_name="X", email=f"a@b.co{injection}")
        pdf = generate_pdf(f'## Perfil\n<link rel="attachment" href="file://{secret}">', profile)
        assert pdf.startswith(b"%PDF")
        assert b"/EmbeddedFile" not in pdf


class TestGeneratePdf:
    @patch("services.pdf_generator.HTML")
    def test_generates_pdf_and_returns_bytes(self, mock_html):
        mock_doc = MagicMock()
        mock_html.return_value = mock_doc

        profile = UserProfile(username="test", full_name="Test")
        result = generate_pdf("## Test", profile)
        assert result == mock_doc.write_pdf.return_value
        mock_html.assert_called_once()
        mock_doc.write_pdf.assert_called_once_with(target=None)


class TestBuildPdfFilename:
    def test_full_name_role_company(self):
        profile = UserProfile(username="test", full_name="Camilo Maestre")
        result = build_pdf_filename(profile, "Senior SWE", "Google")
        assert result.startswith("Camilo_Maestre_Senior_SWE_Google")
        assert result.endswith(".pdf")

    def test_name_only(self):
        profile = UserProfile(username="test", full_name="Juan Perez")
        result = build_pdf_filename(profile)
        assert result == "Juan_Perez.pdf"

    def test_no_especificada_skipped(self):
        profile = UserProfile(username="test", full_name="Ana")
        result = build_pdf_filename(profile, "Dev", "No especificada")
        assert result == "Ana_Dev.pdf"

    def test_special_chars_removed(self):
        profile = UserProfile(username="test", full_name="María José")
        result = build_pdf_filename(profile, "C++ Developer", "@Corp!")
        assert "++" not in result
        assert "@" not in result
        assert "María_José" in result

    def test_empty_fallback(self):
        profile = UserProfile(username="test")
        result = build_pdf_filename(profile)
        assert result == "cv_adaptado.pdf"

    def test_truncation(self):
        profile = UserProfile(username="test", full_name="A" * 60)
        result = build_pdf_filename(profile, "B" * 60, "C" * 60)
        assert len(result) < 200
        assert result.endswith(".pdf")


class TestParseVacancyFields:
    def test_parse_role_and_company(self):
        text = "ROLE: Senior Developer\nCOMPANY: Google\nAbout the Role:\nTest"
        role, company = parse_vacancy_fields(text)
        assert role == "Senior Developer"
        assert company == "Google"

    def test_parse_only_role(self):
        text = "ROLE: Data Engineer\nAbout the Role:\nTest"
        role, company = parse_vacancy_fields(text)
        assert role == "Data Engineer"
        assert company == ""

    def test_parse_empty(self):
        role, company = parse_vacancy_fields("")
        assert role == ""
        assert company == ""


class TestGeminiClientVersioning:
    @patch("services.gemini_client.requests.post")
    def test_v1_uses_legacy_prompt(self, mock_post):
        from services.gemini_client import GeminiClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ROLE: Dev"}]}}]
        }
        mock_post.return_value = mock_response

        client = GeminiClient(api_key="test", prompt_version="v1")
        result = client.analyze_job_posting(text="test vacante")
        assert result == "ROLE: Dev"
        assert "PROHIBIDO" not in result

    @patch("services.gemini_client.requests.post")
    def test_v2_job_parsing_error(self, mock_post):
        from services.gemini_client import GeminiClient, JobParsingError

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ERROR: La entrada no contiene información válida de una vacante."}]}}]
        }
        mock_post.return_value = mock_response

        client = GeminiClient(api_key="test", prompt_version="v2")
        with pytest.raises(JobParsingError):
            client.analyze_job_posting(text="asdfgh")

    @patch("services.gemini_client.requests.post")
    def test_v1_does_not_raise_parsing_error(self, mock_post):
        from services.gemini_client import GeminiClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ERROR: algo raro"}]}}]
        }
        mock_post.return_value = mock_response

        client = GeminiClient(api_key="test", prompt_version="v1")
        result = client.analyze_job_posting(text="test")
        assert result.startswith("ERROR:")

    @patch("services.gemini_client.requests.post")
    def test_v2_polish_prompt_has_verbos_prohibidos(self, mock_post):
        from services.gemini_client import GeminiClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "### Test"}]}}]
        }
        mock_post.return_value = mock_response

        client = GeminiClient(api_key="test", prompt_version="v2")
        client.polish_experience("Dev", "Corp", "2023", "CO", "Remoto", "test")

        call_args = mock_post.call_args[1]["json"]
        prompt_sent = call_args["contents"][0]["parts"][0]["text"]
        assert "Responsable de" in prompt_sent
        assert "Encargado de" in prompt_sent

    @patch("services.gemini_client.requests.post")
    def test_v2_generate_cv_has_una_pagina_rule(self, mock_post):
        from services.gemini_client import GeminiClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "## Perfil"}]}}]
        }
        mock_post.return_value = mock_response

        client = GeminiClient(api_key="test", prompt_version="v2")
        client.generate_cv("vacante", "exp", "skills", "edu")

        call_args = mock_post.call_args[1]["json"]
        prompt_sent = call_args["contents"][0]["parts"][0]["text"]
        assert "UNA PÁGINA" in prompt_sent
        assert "KEYWORDS OBLIGATORIAS" in prompt_sent

    @patch("services.gemini_client.requests.post")
    def test_default_version_is_v3(self, mock_post):
        from services.gemini_client import GeminiClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ROLE: Dev"}]}}]
        }
        mock_post.return_value = mock_response

        client = GeminiClient(api_key="test")
        assert client.prompt_version == "v3"


class TestGeminiClientNetworkErrors:
    @patch("services.gemini_client.requests.post")
    def test_request_uses_timeout(self, mock_post):
        from services.gemini_client import GeminiClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }
        mock_post.return_value = mock_response

        GeminiClient(api_key="test").extract_skills_from_vacancy("vacante")
        assert mock_post.call_args[1]["timeout"]

    @patch("services.gemini_client.requests.post")
    def test_timeout_is_not_retried(self, mock_post):
        import requests

        from services.gemini_client import GeminiClient

        mock_post.side_effect = requests.Timeout()
        with pytest.raises(RuntimeError):
            GeminiClient(api_key="test").extract_skills_from_vacancy("vacante")

    @patch("services.gemini_client.requests.post")
    def test_connection_error_is_retryable(self, mock_post):
        import requests

        from services.gemini_client import GeminiClient
        from utils.retry import RetryableError

        mock_post.side_effect = requests.ConnectionError()
        with pytest.raises(RetryableError):
            GeminiClient(api_key="test").extract_skills_from_vacancy("vacante")


class TestCvPromptKeepsRealTitles:
    @patch("services.gemini_client.requests.post")
    def test_v3_prompt_forbids_replacing_job_titles(self, mock_post):
        from services.gemini_client import GeminiClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "## CV"}]}}]
        }
        mock_post.return_value = mock_response

        GeminiClient(api_key="test", prompt_version="v3").generate_cv("vac", "exp", "sk", "edu")
        prompt_sent = mock_post.call_args[1]["json"]["contents"][0]["parts"][0]["text"]
        assert "CARGOS REALES" in prompt_sent
        assert "TODAS las experiencias deben titularse" not in prompt_sent


def _mock_ok(mock_post, text="ok"):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    mock_post.return_value = mock_response


def _sent_prompt(mock_post) -> str:
    return mock_post.call_args[1]["json"]["contents"][0]["parts"][-1]["text"]


class TestUniversalPrompts:
    @patch("services.gemini_client.requests.post")
    def test_analysis_asks_for_language_and_area(self, mock_post):
        from services.gemini_client import GeminiClient

        _mock_ok(mock_post, "ROLE: Auxiliar")
        GeminiClient(api_key="test", prompt_version="v3").analyze_job_posting(text="vacante")
        prompt = _sent_prompt(mock_post)
        assert "LANGUAGE:" in prompt
        assert "AREA:" in prompt

    @patch("services.gemini_client.requests.post")
    def test_v3_analysis_rejects_non_vacancy(self, mock_post):
        from services.gemini_client import GeminiClient, JobParsingError

        _mock_ok(mock_post, "ERROR: La entrada no contiene información válida de una vacante.")
        with pytest.raises(JobParsingError):
            GeminiClient(api_key="test", prompt_version="v3").analyze_job_posting(text="hola")

    @patch("services.gemini_client.requests.post")
    def test_cv_prompt_is_not_tech_specific(self, mock_post):
        from services.gemini_client import GeminiClient

        _mock_ok(mock_post, "## CV")
        GeminiClient(api_key="test", prompt_version="v3").generate_cv(
            "vac", "exp", "sk", "edu", language="es", area="Administrativa"
        )
        prompt = _sent_prompt(mock_post)
        assert "sector tecnológico" not in prompt
        assert "Technical Skills" not in prompt
        assert "Área profesional: Administrativa" in prompt
        assert "## Habilidades" in prompt
        assert "exactamente 12" not in prompt

    @patch("services.gemini_client.requests.post")
    def test_cv_prompt_uses_english_headings_for_english_vacancy(self, mock_post):
        from services.gemini_client import GeminiClient

        _mock_ok(mock_post, "## CV")
        GeminiClient(api_key="test", prompt_version="v3").generate_cv(
            "vac", "exp", "sk", "edu", language="en", area="Operations"
        )
        prompt = _sent_prompt(mock_post)
        assert "## Professional Summary" in prompt
        assert "## Work Experience" in prompt
        assert "Idioma del CV: en" in prompt

    @patch("services.gemini_client.requests.post")
    def test_cv_prompt_without_language_defers_to_vacancy(self, mock_post):
        from services.gemini_client import GeminiClient

        _mock_ok(mock_post, "## CV")
        GeminiClient(api_key="test", prompt_version="v3").generate_cv("vac", "exp", "sk", "edu")
        prompt = _sent_prompt(mock_post)
        assert "el mismo idioma en que está escrita la vacante" in prompt
        assert "tradúcelos" in prompt

    @patch("services.gemini_client.requests.post")
    def test_polish_v3_is_not_tech_specific_and_forbids_inventing(self, mock_post):
        from services.gemini_client import GeminiClient

        _mock_ok(mock_post, "### X")
        GeminiClient(api_key="test", prompt_version="v3").polish_experience(
            "Auxiliar", "ACME", "2022 - 2024", "Colombia", "Presencial", "facturas"
        )
        prompt = _sent_prompt(mock_post)
        assert "carreras de TI" not in prompt
        assert "NO INVENTES" in prompt

    @patch("services.gemini_client.requests.post")
    def test_cv_import_uses_universal_categories(self, mock_post):
        from config import SKILL_CATEGORIES
        from services.gemini_client import GeminiClient

        _mock_ok(mock_post, "EXPERIENCIAS:")
        GeminiClient(api_key="test").parse_cv_document("cv")
        prompt = _sent_prompt(mock_post)
        assert all(cat in prompt for cat in SKILL_CATEGORIES)
        assert "Lenguajes de Programación" not in prompt


class TestParseVacancyHeader:
    def test_reads_all_header_fields(self):
        from services.pdf_generator import parse_vacancy_header

        text = "ROLE: Auxiliar\nCOMPANY: ACME\nLANGUAGE: es\nAREA: Administrativa\n\nAbout the Role:\nX"
        assert parse_vacancy_header(text) == {
            "ROLE": "Auxiliar",
            "COMPANY": "ACME",
            "LANGUAGE": "es",
            "AREA": "Administrativa",
        }

    def test_tolerates_markdown_bold_and_keeps_first_value(self):
        from services.pdf_generator import parse_vacancy_header

        text = "**ROLE:** Analista\nRequirements:\n- Role: líder\nrole: otro"
        assert parse_vacancy_header(text)["ROLE"] == "Analista"


class TestGenerateDocx:
    def test_docx_structure(self):
        import io

        import docx

        from services.docx_generator import build_docx_filename, generate_docx

        profile = UserProfile(username="a", full_name="Ana Pérez", email="ana@x.co")
        cv_md = (
            "## Perfil Profesional\nAuxiliar **Administrativa**\n"
            "## Experiencia Laboral\n### Auxiliar - ACME | 2022 - 2024\n- Gestioné **facturación**\n"
        )
        document = docx.Document(io.BytesIO(generate_docx(cv_md, profile)))
        styled = [(p.style.name, p.text) for p in document.paragraphs]
        assert ("Normal", "ANA PÉREZ") in styled
        assert ("Heading 1", "Experiencia Laboral") in styled
        assert ("Heading 2", "Auxiliar - ACME | 2022 - 2024") in styled
        assert ("List Bullet", "Gestioné facturación") in styled
        assert build_docx_filename("Ana_Auxiliar.pdf") == "Ana_Auxiliar.docx"
