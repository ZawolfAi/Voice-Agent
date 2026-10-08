"""Construct a configured LLM provider without coupling the agent to a vendor."""

from voice_agent.app.config import Settings
from voice_agent.app.llm.provider import LLMConfigurationError, LLMProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    provider_name = settings.llm_provider.casefold()
    if provider_name == "demo":
        if settings.app_env not in {"development", "test"}:
            raise LLMConfigurationError("The demo LLM provider is development/test only")
        from voice_agent.app.llm.demo_provider import DemoProvider

        return DemoProvider()
    if provider_name in {"openai", "gemini"}:
        if not settings.llm_api_key:
            raise LLMConfigurationError("LLM_API_KEY is required for the selected LLM provider")
        from voice_agent.app.llm.openai_provider import OpenAIProvider

        if provider_name == "gemini":
            return OpenAIProvider(
                api_key=settings.llm_api_key,
                model=settings.llm_model or "gemini-3.5-flash-lite",
                timeout_seconds=settings.llm_timeout_seconds,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                max_retries=0,
            )
        return OpenAIProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model or "gpt-4o-mini",
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise LLMConfigurationError(f"Unsupported LLM provider: {provider_name}")