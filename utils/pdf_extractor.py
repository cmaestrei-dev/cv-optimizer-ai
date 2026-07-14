import logging
import os
import tempfile

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str | None:
    try:
        import pdf_inspector

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        result = pdf_inspector.process_pdf(tmp_path)
        os.unlink(tmp_path)

        if result.markdown:
            return result.markdown
        logger.warning("PDF type=%s, no markdown extracted.", result.pdf_type)
        return None
    except ImportError:
        logger.warning("pdf-inspector not installed, trying pdfplumber fallback.")
        return _fallback_pdfplumber(file_bytes)
    except Exception as e:
        logger.error("pdf-inspector failed: %s", e)
        return None


def _fallback_pdfplumber(file_bytes: bytes) -> str | None:
    try:
        import io

        import pdfplumber

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(pages).strip() or None
    except ImportError:
        logger.warning("pdfplumber not installed.")
        return None
    except Exception as e:
        logger.error("pdfplumber failed: %s", e)
        return None
