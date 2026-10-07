from models import UserProfile
from services.pdf_generator import build_pdf_filename, clean_markdown_output


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


class TestCssTemplate:
    def test_css_is_valid_for_replace_filling(self):
        from services.pdf_generator import CSS_TEMPLATE

        # Se rellena con .replace(): llaves dobles llegarían tal cual y WeasyPrint ignoraría reglas (p. ej. @page).
        assert "{{" not in CSS_TEMPLATE and "}}" not in CSS_TEMPLATE

    def test_page_margins_and_bullets_render(self):
        from weasyprint import HTML

        from services.pdf_generator import CSS_TEMPLATE
        from utils.pdf_extractor import extract_text_from_pdf

        css = CSS_TEMPLATE.replace("{page_size}", "A4")
        doc = HTML(string=f"<html><head><style>{css}</style></head><body><ul><li>Logro</li></ul></body></html>")
        rendered = doc.render()
        assert round(rendered.pages[0]._page_box.margin_left) == 48  # 0.5in
        assert "– Logro" in (extract_text_from_pdf(rendered.write_pdf()) or "")
