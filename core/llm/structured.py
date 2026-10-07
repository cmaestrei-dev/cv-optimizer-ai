import json
import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from core.llm.client import Image, LLMClient

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(RuntimeError):
    pass


def _strip_code_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def generate_structured(
    llm: LLMClient,
    prompt: str,
    schema: type[T],
    *,
    images: tuple[Image, ...] = (),
    cache: bool = True,
) -> T:
    """Pide JSON, lo valida con Pydantic y, si no cumple, pide una corrección una sola vez.

    Se usa el modo JSON simple (json_object) porque es el único que comparten todos los
    proveedores (DeepSeek no acepta json_schema); el esquema va en el prompt.
    """
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    full_prompt = (
        f"{prompt}\n\n"
        "FORMATO DE RESPUESTA: responde ÚNICAMENTE con un objeto JSON válido (json) "
        f"que cumpla este JSON Schema:\n{schema_json}"
    )
    raw = llm.complete(full_prompt, images=images, json_mode=True, temperature=0.0, cache=cache)
    try:
        return schema.model_validate_json(_strip_code_fences(raw))
    except ValidationError as first_error:
        logger.warning("Salida de %s no cumple %s; pidiendo corrección.", llm.label, schema.__name__)
        repair_prompt = (
            f"{full_prompt}\n\nTu respuesta anterior fue:\n{raw}\n\n"
            f"No cumple el esquema por estos errores:\n{first_error}\n\n"
            "Devuelve el JSON corregido, completo, y nada más."
        )
        repaired = llm.complete(repair_prompt, images=images, json_mode=True, temperature=0.0)
        try:
            return schema.model_validate_json(_strip_code_fences(repaired))
        except ValidationError as e:
            raise StructuredOutputError(
                f"{llm.label} no devolvió un {schema.__name__} válido tras corregir: {e}"
            ) from e
