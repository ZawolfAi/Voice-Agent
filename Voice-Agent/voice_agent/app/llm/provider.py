"""Provider contract and sanitized errors for structured language-model calls."""

from typing import Protocol

from voice_agent.app.schemas.extraction import ExtractionContext, IntentExtraction


class LLMProviderError(RuntimeError):
    """A provider call failed; messages must not contain prompts or credentials."""


class LLMConfigurationError(RuntimeError):
    """Provider configuration is missing or unsupported."""


class LLMProvider(Protocol):
    async def extract(
        self, text: str, context: ExtractionContext
    ) -> IntentExtraction:
        """Return validated structured intent and entity extraction."""