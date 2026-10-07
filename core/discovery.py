"""Fase 4 — descubrimiento asistido.

- Sugerir cargos afines al perfil y armar los enlaces de búsqueda de cada portal: la persona los abre
  en SU navegador (sin scraping desde el servidor).
- Bandeja: varias vacantes por enlace → traer, analizar y ordenar por compatibilidad. Cada una queda
  "por revisar" hasta que la persona decide prepararla o descartarla. Nada se envía solo.
"""

import json
import logging
import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from urllib.parse import quote

from pydantic import BaseModel, Field

from core.capture import CaptureError, canonical_url, capture_vacancy
from core.engine.pipeline import analyze, match_summary
from core.llm.client import LLMAuthError, LLMClient
from core.llm.providers import LLMConfigError
from core.llm.structured import generate_structured
from core.profile.snapshot import ProfileSnapshot
from core.tracking import service as tracking
from core.tracking.models import STATUSES
from core.vacancy import NotAVacancyError
from utils.retry import RetryableError

MAX_BATCH = 10
logger = logging.getLogger(__name__)


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def search_links(title: str, city: str = "") -> list[tuple[str, str]]:
    """Enlaces de búsqueda verificados (2026-10-07). Magneto no admite ciudad en la URL, y sus páginas
    /co/trabajos/<cargo> solo existen para cargos populares (las demás dan 500): se usa su buscador."""
    q, c = slug(title), slug(city)
    links = [
        ("LinkedIn", "https://www.linkedin.com/jobs/search?keywords=" + quote(title.strip())
         + (f"&location={quote(city.strip() + ', Colombia')}" if city.strip() else "&location=Colombia")),
        ("Computrabajo", f"https://co.computrabajo.com/trabajo-de-{q}" + (f"-en-{c}" if c else "")),
        ("elempleo", f"https://www.elempleo.com/co/ofertas-empleo/{c + '/' if c else ''}{q}"),
        ("Magneto", "https://www.magneto365.com/co/trabajos/buscar?q=" + quote(title.strip())),
    ]
    return links if q else []


class TitleSuggestions(BaseModel):
    titles: list[str] = Field(default_factory=list)


_TITLES_PROMPT = """Con base en la experiencia real de esta persona, sugiere entre 5 y 8 nombres de cargo \
a los que podría postular en portales de empleo de Colombia (como aparecen en las ofertas: \
"Auxiliar Administrativo", "Asistente de Facturación"...). Incluye sus cargos actuales y cargos afines \
del mismo nivel. No sugieras cargos que exijan experiencia que no tiene.

CARGOS QUE HA TENIDO: {roles}
LOGROS Y HABILIDADES: {evidence}"""


def suggest_titles(llm: LLMClient, profile: ProfileSnapshot) -> list[str]:
    roles = list(dict.fromkeys(e.role for e in profile.experiences))
    evidence = "; ".join([a.text for e in profile.experiences for a in e.achievements][:25] + [s.name for s in profile.skills][:20])
    suggested = generate_structured(
        llm, _TITLES_PROMPT.format(roles=", ".join(roles) or "-", evidence=evidence or "-"), TitleSuggestions
    ).titles
    seen, titles = set(), []
    for title in [*roles, *suggested]:
        key = slug(title)
        if key and key not in seen:
            seen.add(key)
            titles.append(title.strip())
    return titles[:10]


@dataclass
class TriageResult:
    url: str
    status: str  # "agregada" | "repetida" | "error"
    message: str = ""
    application_id: int | None = None
    score: int | None = None


def parse_links(text: str) -> list[str]:
    """Enlaces http(s) de un bloque de texto (uno por línea o mezclados), sin repetir la misma vacante."""
    urls = (canonical_url(u.rstrip(").,;")) for u in re.findall(r"https?://[^\s<>\"']+", text))
    return list(dict.fromkeys(urls))


def triage(
    username: str,
    urls: list[str],
    llm: LLMClient,
    profile: ProfileSnapshot,
    capture: Callable = capture_vacancy,
) -> Iterator[TriageResult]:
    """Procesa cada enlace y lo deja 'por revisar'. Es un generador para mostrar el progreso.

    Los errores de una vacante no detienen el lote; los de configuración de la IA (clave inválida o
    ausente) sí se propagan, porque fallarían igual en todas.
    """
    for url in urls:
        url = canonical_url(url)
        try:
            yield _triage_one(username, url, llm, profile, capture)
        except (LLMAuthError, LLMConfigError):
            raise
        except Exception:  # un enlace raro (o un corte de la BD) no tumba el lote ni su reporte
            logger.exception("Error inesperado en la bandeja con %s", url)
            yield TriageResult(url, "error", "Error inesperado con este enlace. Intenta de nuevo o pega el texto de la vacante.")


def _triage_one(username: str, url: str, llm: LLMClient, profile: ProfileSnapshot, capture: Callable) -> TriageResult:
    if (existing := tracking.find_by_url(username, url)) is not None:
        return _repeated(url, existing)
    try:
        captured = capture(url)
    except CaptureError as e:
        return TriageResult(url, "error", str(e))
    final_url = canonical_url(captured.url)
    if (existing := tracking.find_by_url(username, final_url)) is not None:  # misma oferta tras redirigir
        return _repeated(url, existing)
    try:
        result = analyze(llm, profile, text=captured.text)
    except (LLMAuthError, LLMConfigError):
        raise
    except NotAVacancyError:
        return TriageResult(url, "error", "La página no parece una oferta de empleo.")
    except (RuntimeError, RetryableError):  # saturación, tiempo agotado, respuesta inválida
        logger.warning("No se pudo analizar %s", url, exc_info=True)
        return TriageResult(url, "error", "La IA no pudo analizarla ahora. Intenta de nuevo con este enlace.")
    vacancy, match = result.vacancy, result.match
    application_id = tracking.create_application(  # se guarda la URL final: así un enlace corto y el largo coinciden
        username, role=vacancy.role or captured.title, company=vacancy.company or captured.company,
        platform=captured.platform, url=final_url, vacancy_text=captured.text,
        analysis_json=vacancy.model_dump_json(), match_json=json.dumps(match_summary(match), ensure_ascii=False),
        match_score=match.score, status="por_revisar",
    )
    label = " — ".join(p for p in (vacancy.role, vacancy.company) if p)
    return TriageResult(url, "agregada", label, application_id, match.score)


def _repeated(url: str, existing) -> TriageResult:
    status = STATUSES.get(existing.status, (existing.status, ""))[0].lower()
    return TriageResult(url, "repetida", f"Ya la tienes ({status}): {existing.role}", existing.id, existing.match_score)


def missing_musts(match_json: str, level: str = "no") -> list[str]:
    """Requisitos obligatorios con ese nivel ("no" = no cubiertos, "parcial" = a medias), desde el resumen guardado."""
    try:
        data = json.loads(match_json or "{}")
    except json.JSONDecodeError:
        return []
    return [r["text"] for r in data.get("requirements", []) if r.get("kind") == "obligatorio" and r.get("level") == level]
