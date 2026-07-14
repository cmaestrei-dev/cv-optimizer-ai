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
