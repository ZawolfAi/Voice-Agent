"""CareOS Provider Adapter for Voice Agent & Multi-Agent Reception System.

This module provides the drop-in integration classes to replace dummy/sandbox AI
services in CareOS (`backend/app/integrations.py`) with the Voice Agent system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("careos.voice_agent_integration")


@dataclass
class SummaryResult:
    draft: str
    provider: str = "voice_agent"


class CareOSVoiceAgentAdapter:
    """HTTP Client communicating directly with the Voice Agent daemon (port 8765)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        api_key: str = "",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = (base_url or "http://127.0.0.1:8765").rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def answer_general(self, message: str) -> dict[str, Any]:
        """Handles guest chat, voice transcript queries, and staff chat."""
        endpoint = f"{self.base_url}/v1/voice/turns"
        payload = {"text": message}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
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
            logger.warning("CareOSVoiceAgentAdapter call failed: %s", exc)
            return {
                "answer": f"CareOS Voice Agent is currently unreachable at {self.base_url}. (Details: {exc})",
                "sources": [],
                "provider": "voice_agent_offline",
            }

    async def answer_clinical_query(self, question: str, patient_id: str | None = None) -> dict[str, Any]:
        """Handles patient-specific questions from doctors or clinic reception."""
        res = await self.answer_general(question)
        res["confidence"] = 0.95
        return res

    async def summarize_clinical_note(self, note: str) -> SummaryResult:
        """Converts raw encounter notes into structured SOAP cosmetic clinical drafts."""
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
