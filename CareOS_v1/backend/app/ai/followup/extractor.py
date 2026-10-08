import json
import logging
from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError
from fastapi import HTTPException

from app.ai.followup.contracts import FollowUpExtraction
from app.config import get_settings

logger = logging.getLogger(__name__)


class FollowUpExtractor:
    """Extract structured followup intent from user text using LLM."""

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

    async def extract(self, text: str) -> FollowUpExtraction:
        if not self.client:
            logger.warning("LLM client is unconfigured. Returning unknown followup extraction.")
            raise HTTPException(status_code=503, detail="AI service unconfigured")

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Extract follow-up intent only. "
                            "Return JSON with exactly these fields: "
                            "action, confirmation, followup_type, date, time, "
                            "appointment_id, followup_id, reason. "
                            "action must be one of: create, get, modify, cancel, complete, unknown. "
                            "confirmation must be one of: confirm, reject, unknown. "
                            "Set confirmation=confirm when the user clearly accepts "
                            "or wants to proceed with the current operation. "
                            "Set confirmation=reject when the user clearly refuses "
                            "or stops the current operation. "
                            "Otherwise use unknown. When confirmation=reject, set action=unknown unless the user explicitly asks to cancel. "
                            "Normalize Arabic relative dates: بكرة -> tomorrow, النهارده -> today. "
                            "Extract explicit time exactly when possible. "
                            "If AM/PM is explicit, normalize time to HH:MM format (for example: الساعة 10 الصبح -> 10:00, الساعة 6 بالليل -> 18:00). "
                            "Do not infer missing data. Do not invent dates, times, or IDs. "
                            "Keep missing values null."
                        ),
                    },
                    {
                        "role": "user",
                        "content": text,
                    },
                ],
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            return FollowUpExtraction.model_validate(data)
        except OpenAIError as exc:
            logger.error(f"Provider unavailable: {exc}")
            raise HTTPException(status_code=503, detail="AI service unavailable")
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error(f"Invalid model output: {exc}")
            raise HTTPException(status_code=502, detail="Invalid extraction output")
        except Exception as exc:
            logger.error(f"Error during followup extraction: {exc}")
            raise HTTPException(status_code=500, detail="Internal extraction error")

