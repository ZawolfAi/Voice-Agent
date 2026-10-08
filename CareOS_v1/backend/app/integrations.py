"""Replaceable sandbox adapters for external clinical services.

Production adapters belong behind these protocols; no provider key is exposed to
the browser or required for the demo environment.
"""
from dataclasses import dataclass

import httpx

from .config import get_settings


@dataclass
class SummaryResult:
    draft: str
    provider: str = "sandbox"


class ClinicalSummaryProvider:
    async def summarize(self, note: str) -> SummaryResult:
        settings = get_settings()
        if settings.is_production and settings.ai_provider.strip().lower() in {"", "unconfigured", "sandbox"}:
            raise RuntimeError("AI clinical note provider is not configured")
        if settings.ai_provider.strip().lower() not in {"", "unconfigured", "sandbox"}:
            if not settings.ai_api_url or not settings.ai_api_key:
                raise RuntimeError("AI clinical note provider credentials are not configured")
            headers = {"Authorization": f"Bearer {settings.ai_api_key}"}
            payload = {"model": settings.ai_model, "input": note, "task": "clinical_note_draft"}
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(settings.ai_api_url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
            return SummaryResult(draft=str(result.get("draft") or result.get("text") or ""), provider=settings.ai_provider)
        excerpt = note.strip().replace("\n", " ")[:500]
        return SummaryResult(draft=f"Clinical draft (review required): {excerpt}")


class RagProvider:
    async def answer(self, question: str) -> dict[str, object]:
        return {"answer": f"Sandbox response for: {question}. Review applicable local protocol before acting.", "confidence": 0.0, "sources": [], "provider": "sandbox"}

    async def answer_general(self, message: str) -> dict[str, object]:
        settings = get_settings()
        configured = settings.ai_provider.strip().lower()
        if configured not in {"", "unconfigured", "sandbox"}:
            if not settings.ai_api_key:
                raise RuntimeError("General assistant provider credentials are not configured")
            headers = {"Authorization": f"Bearer {settings.ai_api_key}"}
            if configured == "openai":
                endpoint = settings.ai_api_url.strip() or "https://api.openai.com/v1/chat/completions"
                payload = {
                    "model": settings.ai_model or "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are the CareOS public assistant. Reply in the user's language and keep the answer concise. "
                                "Provide general information only, not diagnoses, prescriptions, or personalized treatment. "
                                "For emergencies or urgent symptoms, advise contacting local emergency services or a clinician. "
                                "Do not claim access to patient records."
                            ),
                        },
                        {"role": "user", "content": message},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                }
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(endpoint, headers=headers, json=payload)
                    response.raise_for_status()
                    result = response.json()
                choices = result.get("choices") or []
                answer = choices[0].get("message", {}).get("content") if choices else None
                if not answer:
                    raise RuntimeError("OpenAI assistant returned an empty response")
                return {"answer": str(answer), "sources": [], "provider": "openai"}

            if not settings.ai_api_url:
                raise RuntimeError("General assistant provider URL is not configured")
            payload = {"model": settings.ai_model, "input": message, "task": "general_chat"}
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(settings.ai_api_url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
            answer = result.get("answer") or result.get("response") or result.get("text") or result.get("draft")
            if not answer:
                raise RuntimeError("General assistant provider returned an empty response")
            return {"answer": str(answer), "sources": [], "provider": settings.ai_provider}
        if settings.is_production:
            raise RuntimeError("General assistant provider is not configured")
        return {
            "answer": f"Demo assistant received: {message}. Configure AI_PROVIDER to enable generated replies.",
            "sources": [],
            "provider": "sandbox",
        }


class OcrProvider:
    async def extract(self, filename: str, content: bytes) -> str:
        if not content:
            return "No content provided."
        try:
            url = "http://localhost:8000/api/v1/process"
            files = {"file": (filename, content, "application/octet-stream")}
            
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(url, files=files)
                response.raise_for_status()
                result = response.json()
            
            extracted = result.get("extracted_data", {})
            import json
            return json.dumps(extracted, ensure_ascii=False, indent=2)
            
        except Exception as e:
            return f"ZaWolf AI Extraction Failed: {str(e)}"


class NotificationProvider:
    async def queue(self, channel: str, recipient: str, body: str) -> dict[str, str]:
        return {"status": "queued", "channel": channel, "provider": "sandbox"}


class SpeechToTextProvider:
    """Provider boundary; concrete ASR integrations must implement it server-side."""

    name = "unconfigured"

    async def transcribe(self, audio: bytes, *, language: str = "ar-EG") -> dict[str, object]:
        raise RuntimeError("Speech-to-text provider is not configured")

    async def start_streaming(self, *, language: str = "ar-EG") -> dict[str, object]:
        raise RuntimeError("Speech-to-text streaming provider is not configured")


class ConfiguredSpeechToTextProvider(SpeechToTextProvider):
    def __init__(self, name: str) -> None:
        self.name = name

    async def transcribe(self, audio: bytes, *, language: str = "ar-EG") -> dict[str, object]:
        settings = get_settings()
        if not settings.speech_to_text_api_url or not settings.speech_to_text_api_key:
            raise RuntimeError("Speech-to-text provider credentials are not configured")
        headers = {"Authorization": f"Bearer {settings.speech_to_text_api_key}"}
        files = {"file": ("recording.webm", audio, "audio/webm")}
        data = {"language": language, "enable_diarization": str(settings.speech_to_text_diarization).lower()}
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(settings.speech_to_text_api_url, headers=headers, files=files, data=data)
            response.raise_for_status()
            payload = response.json()
        return {"text": payload.get("text", payload.get("transcript", "")), "confidence": payload.get("confidence"), "provider": self.name}


class OpenAISpeechToTextProvider(SpeechToTextProvider):
    """OpenAI audio-transcriptions adapter; credentials stay on the server."""

    name = "openai"

    async def transcribe(self, audio: bytes, *, language: str = "ar-EG") -> dict[str, object]:
        settings = get_settings()
        api_key = settings.speech_to_text_api_key or (
            settings.ai_api_key if settings.ai_provider.strip().lower() == "openai" else ""
        )
        if not api_key:
            raise RuntimeError("Speech-to-text provider credentials are not configured")
        endpoint = settings.speech_to_text_api_url.strip() or "https://api.openai.com/v1/audio/transcriptions"
        language_code = language.split("-", 1)[0].lower()
        headers = {"Authorization": f"Bearer {api_key}"}
        files = {"file": ("recording.webm", audio, "audio/webm")}
        data = {"model": settings.speech_to_text_model, "language": language_code}
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(endpoint, headers=headers, files=files, data=data)
            response.raise_for_status()
            payload = response.json()
        return {"text": payload.get("text", ""), "confidence": payload.get("confidence"), "provider": self.name}


class BelMasryProvider(ConfiguredSpeechToTextProvider):
    """BelMasry-compatible HTTP adapter; credentials remain server-side."""

    def __init__(self) -> None:
        super().__init__("belmasry")


def get_speech_to_text_provider() -> SpeechToTextProvider:
    settings = get_settings()
    configured = settings.speech_to_text_provider.strip().lower()
    if configured in {"", "unconfigured"}:
        if settings.ai_provider.strip().lower() == "openai":
            return OpenAISpeechToTextProvider()
        return SpeechToTextProvider()
    if configured == "openai":
        return OpenAISpeechToTextProvider()
    return BelMasryProvider() if configured == "belmasry" else ConfiguredSpeechToTextProvider(configured)


summary_provider = ClinicalSummaryProvider()
rag_provider = RagProvider()
ocr_provider = OcrProvider()
notification_provider = NotificationProvider()
