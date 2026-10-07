"""Errores del dominio → (código HTTP, mensaje para la persona). Una sola tabla para la API y el trabajador.

Los mensajes no exponen detalles internos (nombres de variables, respuestas del proveedor).
"""

from core.capture import CaptureError
from core.llm import LLMConfigError, StructuredOutputError
from core.llm.client import LLMAuthError, LLMUnavailableError
from core.profile.repository import NotFoundError, UserExistsError
from core.usage import QuotaExceededError
from core.vacancy import NotAVacancyError
from utils.retry import RetryableError


class UserInputError(ValueError):
    """Algo que la persona debe corregir; el mensaje se le muestra tal cual."""


AI_UNAVAILABLE = "La IA no está disponible en este momento. Intenta de nuevo más tarde."


def describe(exc: BaseException) -> tuple[int, str] | None:
    """None si no es un error conocido (se trata como error interno)."""
    if isinstance(exc, NotFoundError):
        return 404, "No encontrado"
    if isinstance(exc, UserExistsError):
        return 409, "Ya existe"
    if isinstance(exc, UserInputError | CaptureError):
        return 422, str(exc)
    if isinstance(exc, NotAVacancyError):
        return 422, "El texto no parece una oferta de empleo."
    if isinstance(exc, QuotaExceededError):
        return 429, str(exc)
    if isinstance(exc, RetryableError):
        return 503, "Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo."
    if isinstance(exc, LLMAuthError | LLMConfigError | LLMUnavailableError):
        return 503, AI_UNAVAILABLE
    if isinstance(exc, StructuredOutputError):
        return 502, "La IA devolvió una respuesta inválida. Intenta de nuevo."
    return None
