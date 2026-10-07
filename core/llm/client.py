import base64
import hashlib
import json
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass

import requests

from config import LLM_TIMEOUT_SECONDS
from utils.retry import RetryableError, retry_with_backoff

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMUnavailableError(RuntimeError):
    """El proveedor no respondió bien (tiempo agotado, error HTTP no reintentable, respuesta rara)."""


class LLMAuthError(RuntimeError):
    """La API key no es válida, fue revocada o no tiene permisos."""


def is_auth_failure(status_code: int, body: str) -> bool:
    # Google responde 400 API_KEY_INVALID (clave clásica) o 401 (clave "AQ." inválida/revocada).
    return status_code in (401, 403) or (status_code == 400 and "API_KEY_INVALID" in body)
_CACHE_MAX_ENTRIES = 256


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    api_key_env: str
    default_model: str
    supports_images: bool


@dataclass(frozen=True)
class Image:
    data: bytes
    mime: str


class _ResponseCache:
    """LRU en memoria del proceso: analizar dos veces la misma vacante no gasta cuota."""

    def __init__(self, max_entries: int = _CACHE_MAX_ENTRIES):
        self._data: OrderedDict[str, str] = OrderedDict()
        self._max = max_entries
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


response_cache = _ResponseCache()


class LLMClient:
    """Cliente de chat para cualquier API compatible con OpenAI (Gemini, DeepSeek, OpenAI...)."""

    def __init__(self, spec: ProviderSpec, api_key: str, model: str):
        self.spec = spec
        self.model = model
        self._api_key = api_key

    @property
    def label(self) -> str:
        return f"{self.spec.name}:{self.model}"

    def complete(
        self,
        prompt: str,
        *,
        images: tuple[Image, ...] = (),
        json_mode: bool = False,
        temperature: float = 0.2,
        cache: bool = False,
    ) -> str:
        if images and not self.spec.supports_images:
            raise ValueError(f"El proveedor {self.spec.name} no acepta imágenes.")

        content: str | list[dict] = prompt
        if images:
            content = [{"type": "text", "text": prompt}] + [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.mime};base64,{base64.b64encode(img.data).decode()}"
                    },
                }
                for img in images
            ]
        body: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        cache_key = ""
        if cache:
            cache_key = hashlib.sha256(
                (self.spec.base_url + json.dumps(body, sort_keys=True)).encode()
            ).hexdigest()
            cached = response_cache.get(cache_key)
            if cached is not None:
                return cached

        text = self._post(body)
        if cache:
            response_cache.put(cache_key, text)
        return text

    @retry_with_backoff()
    def _post(self, body: dict) -> str:
        url = f"{self.spec.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            response = requests.post(url, headers=headers, json=body, timeout=LLM_TIMEOUT_SECONDS)
        except requests.ConnectionError as e:
            raise RetryableError(f"Error de conexión con {self.spec.name}: {e}") from e
        except requests.Timeout as e:
            raise LLMUnavailableError(f"{self.spec.name} tardó demasiado en responder.") from e

        if is_auth_failure(response.status_code, response.text):
            raise LLMAuthError(
                f"La API key de {self.spec.name} no es válida o fue revocada. Revisa "
                f"{self.spec.api_key_env} en los secretos y que el campo de la barra lateral esté vacío."
            )
        if response.status_code in _RETRYABLE_STATUS:
            raise RetryableError(f"{self.spec.name} HTTP {response.status_code}: {response.text[:200]}")
        if response.status_code != 200:
            raise LLMUnavailableError(f"{self.spec.name} HTTP {response.status_code}: {response.text[:500]}")

        try:
            text = response.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise LLMUnavailableError(f"Respuesta inesperada de {self.spec.name}: {response.text[:300]}") from e
        if not text.strip():
            # DeepSeek documenta respuestas vacías ocasionales en modo JSON.
            raise RetryableError(f"{self.spec.name} devolvió una respuesta vacía.")
        return text.strip()
