import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from core.llm import (
    PROVIDERS,
    Image,
    LLMClient,
    LLMConfigError,
    StructuredOutputError,
    generate_structured,
    get_llm,
    resolve_task_target,
    response_cache,
)
from utils.retry import RetryableError


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in ("LLM_EXTRACT", "LLM_WRITE", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("utils.retry.time.sleep", lambda _s: None)
    response_cache.clear()


def _response(status=200, content="ok"):
    resp = MagicMock()
    resp.status_code = status
    resp.text = json.dumps({"error": "x"}) if status != 200 else ""
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def _client(provider="gemini"):
    return LLMClient(PROVIDERS[provider], "secret-key-123", "model-x")


class TestProviderResolution:
    def test_defaults_to_gemini_with_default_model(self):
        assert resolve_task_target("extract") == ("gemini", PROVIDERS["gemini"].default_model)

    def test_provider_and_model_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_WRITE", "deepseek:deepseek-pro")
        assert resolve_task_target("write") == ("deepseek", "deepseek-pro")

    def test_provider_only_uses_its_default_model(self, monkeypatch):
        monkeypatch.setenv("LLM_WRITE", "DeepSeek")
        assert resolve_task_target("write") == ("deepseek", "deepseek-flash")

    def test_unknown_provider(self, monkeypatch):
        monkeypatch.setenv("LLM_EXTRACT", "skynet")
        with pytest.raises(LLMConfigError):
            resolve_task_target("extract")

    def test_missing_api_key(self):
        with pytest.raises(LLMConfigError):
            get_llm("extract")

    def test_override_key_wins(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "server")
        llm = get_llm("extract", api_key_overrides={"gemini": "user"})
        assert llm._api_key == "user"


class TestLLMClient:
    @patch("core.llm.client.requests.post")
    def test_openai_compatible_request(self, mock_post):
        mock_post.return_value = _response(content="hola")
        assert _client().complete("prompt", json_mode=True) == "hola"
        url = mock_post.call_args[0][0]
        kwargs = mock_post.call_args[1]
        assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer secret-key-123"
        assert kwargs["json"]["response_format"] == {"type": "json_object"}
        assert kwargs["timeout"]

    @patch("core.llm.client.requests.post")
    def test_images_are_sent_as_data_urls(self, mock_post):
        mock_post.return_value = _response()
        _client().complete("lee esto", images=(Image(b"\x89PNG", "image/png"),))
        content = mock_post.call_args[1]["json"]["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "lee esto"}
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")

    def test_provider_without_images_rejects_them(self):
        with pytest.raises(ValueError):
            _client("deepseek").complete("x", images=(Image(b"x", "image/png"),))

    @patch("core.llm.client.requests.post")
    def test_rate_limit_is_retried_then_raised(self, mock_post):
        mock_post.return_value = _response(status=429)
        with pytest.raises(RetryableError):
            _client().complete("x")
        assert mock_post.call_count == 3

    @patch("core.llm.client.requests.post")
    def test_client_error_does_not_leak_api_key(self, mock_post):
        mock_post.return_value = _response(status=400)
        with pytest.raises(RuntimeError) as exc:
            _client().complete("x")
        assert "secret-key-123" not in str(exc.value)

    @patch("core.llm.client.requests.post")
    def test_empty_content_is_retryable(self, mock_post):
        mock_post.side_effect = [_response(content=""), _response(content="ya")]
        assert _client().complete("x") == "ya"

    @patch("core.llm.client.requests.post")
    def test_cache_avoids_repeated_calls(self, mock_post):
        mock_post.return_value = _response(content="r")
        llm = _client()
        llm.complete("igual", cache=True)
        llm.complete("igual", cache=True)
        llm.complete("igual")
        assert mock_post.call_count == 2


class _Pet(BaseModel):
    name: str
    age: int


class TestGenerateStructured:
    @patch("core.llm.client.requests.post")
    def test_valid_json(self, mock_post):
        mock_post.return_value = _response(content='```json\n{"name": "Luna", "age": 3}\n```')
        pet = generate_structured(_client(), "dame una mascota", _Pet)
        assert pet == _Pet(name="Luna", age=3)
        prompt = mock_post.call_args[1]["json"]["messages"][0]["content"]
        assert "json" in prompt.lower()
        assert '"age"' in prompt

    @patch("core.llm.client.requests.post")
    def test_repairs_once(self, mock_post):
        mock_post.side_effect = [
            _response(content='{"name": "Luna"}'),
            _response(content='{"name": "Luna", "age": 3}'),
        ]
        assert generate_structured(_client(), "x", _Pet).age == 3
        repair_prompt = mock_post.call_args[1]["json"]["messages"][0]["content"]
        assert "age" in repair_prompt and "anterior" in repair_prompt

    @patch("core.llm.client.requests.post")
    def test_gives_up_after_repair(self, mock_post):
        mock_post.return_value = _response(content='{"nope": true}')
        with pytest.raises(StructuredOutputError):
            generate_structured(_client(), "x", _Pet)
