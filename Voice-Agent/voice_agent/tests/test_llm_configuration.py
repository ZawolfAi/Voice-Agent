from typing import Any

import pytest

from voice_agent.app.config import Settings
from voice_agent.app.llm.factory import create_llm_provider
from voice_agent.app.llm.provider import LLMConfigurationError


def test_gemini_provider_uses_google_compatible_endpoint_and_default_model(
    monkeypatch: Any,
) -> None:
    from voice_agent.app.llm import openai_provider

    captured: dict[str, Any] = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(openai_provider, "AsyncOpenAI", FakeAsyncOpenAI)
    provider = create_llm_provider(
        Settings(
            _env_file=None,
            llm_provider="GEMINI",
            llm_api_key="not-a-real-key",
        )
    )

    assert isinstance(provider, openai_provider.OpenAIProvider)
    assert captured == {
        "api_key": "not-a-real-key",
        "timeout": 20.0,
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "max_retries": 0,
    }
    assert provider._model == "gemini-3.5-flash-lite"


def test_gemini_provider_accepts_explicit_model(monkeypatch: Any) -> None:
    from voice_agent.app.llm import openai_provider

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

    monkeypatch.setattr(openai_provider, "AsyncOpenAI", FakeAsyncOpenAI)
    provider = create_llm_provider(
        Settings(
            _env_file=None,
            llm_provider="gemini",
            llm_api_key="not-a-real-key",
            llm_model="gemini-custom-test-model",
        )
    )
    assert provider._model == "gemini-custom-test-model"


def test_gemini_provider_requires_api_key() -> None:
    with pytest.raises(LLMConfigurationError, match="LLM_API_KEY"):
        create_llm_provider(
            Settings(_env_file=None, llm_provider="gemini", llm_api_key=None)
        )


def test_openai_provider_keeps_its_default_model(monkeypatch: Any) -> None:
    from voice_agent.app.llm import openai_provider

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

    monkeypatch.setattr(openai_provider, "AsyncOpenAI", FakeAsyncOpenAI)
    provider = create_llm_provider(
        Settings(_env_file=None, llm_provider="openai", llm_api_key="fake-key")
    )
    assert provider._model == "gpt-4o-mini"