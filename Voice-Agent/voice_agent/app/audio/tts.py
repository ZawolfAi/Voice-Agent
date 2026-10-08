"""Text-to-speech synthesis using Gemini TTS."""

from __future__ import annotations

import logging
from typing import Any

from voice_agent.app.config import Settings

logger = logging.getLogger(__name__)

TTS_MODEL = "gemini-3.8-flash-tts"


async def generate_speech_audio(
    text: str,
    settings: Settings,
    *,
    client_factory: Any | None = None,
) -> tuple[bytes, str] | None:
    """Generate spoken audio (WAV) from text using Gemini TTS."""
    clean_text = text.strip()
    if not clean_text:
        return None

    if settings.llm_provider.casefold() != "gemini" or not settings.llm_api_key:
        logger.debug("TTS skipped: Gemini provider or API key not configured")
        return None

    try:
        if client_factory is not None:
            client = client_factory(api_key=settings.llm_api_key)
        else:
            from google import genai

            client = genai.Client(api_key=settings.llm_api_key)

        response = await client.aio.models.generate_content(
            model=TTS_MODEL,
            contents=clean_text,
        )

        if not response.candidates:
            return None

        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            return None

        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.data:
                mime_type = part.inline_data.mime_type or "audio/wav"
                return part.inline_data.data, mime_type

        return None
    except Exception as exc:
        logger.warning("tts.generate_speech_audio.failed (%s: %s)", type(exc).__name__, exc)
        return None
