import os
from typing import Literal

from config import GEMINI_MODEL
from core.llm.client import LLMClient, ProviderSpec

# Agregar un proveedor compatible con OpenAI = agregar una línea aquí.
PROVIDERS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GEMINI_API_KEY",
        default_model=GEMINI_MODEL,
        supports_images=True,
    ),
    "deepseek": ProviderSpec(
        name="deepseek",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-flash",
        supports_images=False,
    ),
}

# extract: entender vacantes, parsear y verificar (barato, determinista)
# write: redactar el CV (donde más importa la calidad)
Task = Literal["extract", "write"]


class LLMConfigError(RuntimeError):
    pass


def resolve_task_target(task: Task) -> tuple[str, str]:
    """Lee LLM_EXTRACT / LLM_WRITE con formato 'proveedor' o 'proveedor:modelo'. Por defecto: gemini."""
    raw = os.environ.get(f"LLM_{task.upper()}", "").strip() or "gemini"
    provider, _, model = raw.partition(":")
    provider = provider.strip().lower()
    if provider not in PROVIDERS:
        raise LLMConfigError(
            f"Proveedor de IA desconocido en LLM_{task.upper()}: '{provider}'. "
            f"Opciones: {', '.join(PROVIDERS)}."
        )
    return provider, model.strip() or PROVIDERS[provider].default_model


def get_llm(task: Task, api_key_overrides: dict[str, str] | None = None) -> LLMClient:
    provider, model = resolve_task_target(task)
    spec = PROVIDERS[provider]
    api_key = ((api_key_overrides or {}).get(provider) or os.environ.get(spec.api_key_env, "")).strip()
    if not api_key:
        raise LLMConfigError(f"Falta la API key de {provider} ({spec.api_key_env}).")
    return LLMClient(spec, api_key, model)
