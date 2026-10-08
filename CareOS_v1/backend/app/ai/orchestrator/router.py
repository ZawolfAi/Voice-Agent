import json
import logging
from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from app.ai.orchestrator.contracts import IntentResult, IntentType
from app.config import get_settings

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = (
    "Classify the user's request into exactly one intent: booking, followup, unknown.\n"
    "booking = appointment booking, rescheduling, cancellation, availability.\n"
    "followup = patient follow-up creation, retrieval, modification, cancellation, completion.\n"
    "unknown = anything else.\n"
    "Return JSON only: {\"intent\":\"booking|followup|unknown\"}"
)


class IntentRouter:
    """Classifies user messages into intent types (booking, followup, unknown) using LLM."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.ai_api_key or "unconfigured"
        self.base_url = base_url or settings.ai_base_url or settings.ai_api_url or None
        self.model = model or settings.ai_model or "groq-default"

        if self.api_key and self.api_key != "unconfigured":
            kw = {"api_key": self.api_key}
            if self.base_url:
                kw["base_url"] = self.base_url
            self.client = AsyncOpenAI(**kw)
        else:
            self.client = None

    async def classify(self, text: str) -> IntentResult:
        """Classify user text into IntentResult."""
        if not self.client:
            logger.warning("LLM client is unconfigured in IntentRouter. Returning UNKNOWN intent.")
            return IntentResult(intent=IntentType.UNKNOWN)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)

            # Extract intent value safely
            raw_intent = data.get("intent", "").lower().strip() if isinstance(data, dict) else ""
            if raw_intent in {IntentType.BOOKING.value, IntentType.FOLLOWUP.value, IntentType.UNKNOWN.value}:
                return IntentResult(intent=IntentType(raw_intent))

            logger.warning(f"Unrecognized intent string returned by LLM: '{raw_intent}'. Treating as UNKNOWN.")
            return IntentResult(intent=IntentType.UNKNOWN)

        except (OpenAIError, json.JSONDecodeError, ValidationError, Exception) as exc:
            logger.error(f"Error in IntentRouter during classification: {exc}")
            return IntentResult(intent=IntentType.UNKNOWN)
