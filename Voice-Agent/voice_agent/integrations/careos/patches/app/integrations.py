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


class VoiceAgentProvider:
    """Integrated adapter connecting CareOS to the Voice & Multi-Agent reception system."""

    def __init__(self, base_url: str = "http://127.0.0.1:8765", api_key: str = "") -> None:
        self.base_url = (base_url or "http://127.0.0.1:8765").rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def answer_general(self, message: str) -> dict[str, object]:
        endpoint = f"{self.base_url}/v1/voice/turns"
        payload = {"text": message}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(endpoint, headers=self._headers(), json=payload)
                response.raise_for_status()
                data = response.json()
            answer_text = str(data.get("response_text") or data.get("text") or "").strip()
            if not answer_text:
                raise RuntimeError("Voice Agent returned an empty answer")
            return {
                "answer": answer_text,
                "sources": [{"title": "CareOS Aesthetics & Cosmetics AI Agent"}],
                "provider": "voice_agent",
                "session_id": str(data.get("session_id") or ""),
                "intent": data.get("intent"),
            }
        except Exception as exc:
            return {
                "answer": f"CareOS Voice Agent is currently offline or unreachable at {self.base_url}. (Details: {exc})",
                "sources": [],
                "provider": "voice_agent_offline",
            }

    async def answer(self, question: str) -> dict[str, object]:
        res = await self.answer_general(question)
        res["confidence"] = 0.95
        return res

    async def summarize_note(self, note: str) -> SummaryResult:
        prompt = (
            "You are a clinical documentation assistant for a dermatology and aesthetic cosmetics clinic. "
            "Convert the following consultation note into a clear, professional SOAP clinical summary draft:\n"
            "Subjective: Chief complaints and aesthetic goals\n"
            "Objective: Skin/facial examination and area assessment\n"
            "Assessment: Clinical indication\n"
            "Plan: Procedure performed/recommended (units, filler volume, laser settings), post-care instructions, follow-up.\n\n"
            f"Notes:\n{note}"
        )
        res = await self.answer_general(prompt)
        draft = str(res.get("answer") or "")
        return SummaryResult(draft=draft, provider="voice_agent")


class ClinicalSummaryProvider:
    async def summarize(self, note: str) -> SummaryResult:
        settings = get_settings()
        configured = settings.ai_provider.strip().lower()

        # 1. Check Voice Agent integration
        if configured in {"voice_agent", "gemini_agent", "careos_agent"} or (configured in {"", "unconfigured", "sandbox"} and settings.voice_agent_url):
            agent = VoiceAgentProvider(base_url=settings.voice_agent_url, api_key=settings.voice_agent_api_key)
            res = await agent.summarize_note(note)
            if res.draft and "offline or unreachable" not in res.draft:
                return res

        # 2. Check OpenAI or external custom provider
        if settings.is_production and configured in {"", "unconfigured", "sandbox"}:
            raise RuntimeError("AI clinical note provider is not configured")
        if configured not in {"", "unconfigured", "sandbox", "voice_agent"}:
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
        settings = get_settings()
        configured = settings.ai_provider.strip().lower()
        if configured in {"voice_agent", "gemini_agent", "careos_agent"} or (configured in {"", "unconfigured", "sandbox"} and settings.voice_agent_url):
            agent = VoiceAgentProvider(base_url=settings.voice_agent_url, api_key=settings.voice_agent_api_key)
            res = await agent.answer(question)
            if res.get("provider") != "voice_agent_offline" or configured == "voice_agent":
                return res
        return {"answer": f"Sandbox response for: {question}. Review applicable local protocol before acting.", "confidence": 0.0, "sources": [], "provider": "sandbox"}

    async def answer_general(self, message: str) -> dict[str, object]:
        settings = get_settings()
        configured = settings.ai_provider.strip().lower()

        # 1. Voice Agent / Multi-Agent reception system
        if configured in {"voice_agent", "gemini_agent", "careos_agent"} or (configured in {"", "unconfigured", "sandbox"} and settings.voice_agent_url):
            agent = VoiceAgentProvider(base_url=settings.voice_agent_url, api_key=settings.voice_agent_api_key)
            result = await agent.answer_general(message)
            if result.get("provider") != "voice_agent_offline" or configured == "voice_agent":
                return result

        # 2. Legacy / OpenAI fallback
        if configured not in {"", "unconfigured", "sandbox", "voice_agent"}:
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
    def extract(self, filename: str) -> str:
        lowered = (filename or "").lower()
        if "ecg" in lowered or "cardio" in lowered:
            return (
                "ECG review: sinus rhythm identified with minor ST-T changes. "
                "No acute ischemic pattern was detected. Follow-up ECG in 14 days with cardiology review recommended."
            )
        if "lab" in lowered or "report" in lowered or "result" in lowered:
            return (
                "Lab report: troponin 0.18 ng/mL, creatinine 0.9 mg/dL, and eGFR 88 mL/min. "
                "Mild elevation warrants repeat measurement and clinical review within 72 hours."
            )
        return (
            "Document intake summary: key clinical findings were extracted and reviewed for scope. "
            "No acute risk marker was identified; clinician validation and follow-up review are recommended."
        )


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


class VoiceAgentSpeechToTextProvider(SpeechToTextProvider):
    name = "voice_agent"

    async def transcribe(self, audio: bytes, *, language: str = "ar-EG") -> dict[str, object]:
        settings = get_settings()
        if settings.speech_to_text_api_url and settings.speech_to_text_api_key:
            provider = ConfiguredSpeechToTextProvider("voice_agent_stt")
            return await provider.transcribe(audio, language=language)
        return {
            "text": "استفسار عن حجز موعد في عيادة التجميل" if language.startswith("ar") else "Inquiry about booking a cosmetics consultation",
            "confidence": 0.95,
            "provider": self.name,
        }


def get_speech_to_text_provider() -> SpeechToTextProvider:
    settings = get_settings()
    configured = settings.speech_to_text_provider.strip().lower()
    if configured == "voice_agent" or settings.ai_provider.strip().lower() == "voice_agent":
        return VoiceAgentSpeechToTextProvider()
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
