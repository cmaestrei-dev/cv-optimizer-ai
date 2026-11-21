import os
from typing import Literal

from config import GEMINI_MODEL
from core.llm.client import FallbackLLM, LLMClient, ProviderSpec

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


def _target(var: str, raw: str) -> tuple[str, str]:
    provider, _, model = raw.partition(":")
    provider = provider.strip().lower()
    if provider not in PROVIDERS:
        raise LLMConfigError(f"Proveedor de IA desconocido en {var}: '{provider}'. Opciones: {', '.join(PROVIDERS)}.")
    return provider, model.strip() or PROVIDERS[provider].default_model


def resolve_task_target(task: Task) -> tuple[str, str]:
    """Lee LLM_EXTRACT / LLM_WRITE con formato 'proveedor' o 'proveedor:modelo'. Por defecto: gemini."""
    return _target(f"LLM_{task.upper()}", os.environ.get(f"LLM_{task.upper()}", "").strip() or "gemini")


def fallback_target() -> tuple[str, str] | None:
    """LLM_FALLBACK ('proveedor' o 'proveedor:modelo'): el que responde cuando el principal no puede."""
    raw = os.environ.get("LLM_FALLBACK", "").strip()
    return _target("LLM_FALLBACK", raw) if raw else None


def _key(provider: str, overrides: dict[str, str] | None) -> str:
    return ((overrides or {}).get(provider) or os.environ.get(PROVIDERS[provider].api_key_env, "")).strip()


def get_llm(task: Task, api_key_overrides: dict[str, str] | None = None) -> LLMClient | FallbackLLM:
    provider, model = resolve_task_target(task)
    spec = PROVIDERS[provider]
    api_key = _key(provider, api_key_overrides)
    if not api_key:
        raise LLMConfigError(f"Falta la API key de {provider} ({spec.api_key_env}).")
    client = LLMClient(spec, api_key, model)
    backup = fallback_target()
    if backup and backup != (provider, model) and (backup_key := _key(backup[0], api_key_overrides)):
        return FallbackLLM(client, LLMClient(PROVIDERS[backup[0]], backup_key, backup[1]))
    return client
