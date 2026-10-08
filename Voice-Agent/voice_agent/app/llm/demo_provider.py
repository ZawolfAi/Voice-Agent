"""Small offline extractor for exercising the development UI without API costs.

This intentionally recognizes only a few sample appointment phrases. It is not an
LLM and must not be used for real patient conversations.
"""

from __future__ import annotations

import re
import unicodedata

from voice_agent.app.schemas.extraction import ExtractionContext, IntentExtraction
from voice_agent.app.schemas.requests import Intent


class DemoProvider:
    """Rule-based sample extractor for local workflow testing only."""

    async def extract(self, text: str, context: ExtractionContext) -> IntentExtraction:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        normalized = normalized.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        is_booking = context.current_intent == Intent.BOOK_APPOINTMENT or any(
            token in normalized
            for token in ("book", "appointment", "cosmetic", "botox", "filler", "laser", "cardiolog", "heart doctor", "حجز", "ميعاد", "تجميل", "بوتوكس", "فيلر", "ليزر", "نضارة")
        )
        if not is_booking:
            return IntentExtraction(intent=Intent.UNKNOWN)

        specialty = None
        if any(token in normalized for token in ("cosmetic", "botox", "filler", "laser", "skin glow", "تجميل", "بوتوكس", "فيلر", "ليزر", "نضارة")):
            specialty = "cosmetics"
        elif any(token in normalized for token in ("cardiolog", "heart doctor", "دكتور قلب", "طبيب قلب")):
            specialty = "cardiology"
        elif any(token in normalized for token in ("dermatolog", "skin doctor", "جلدية", "جلد")):
            specialty = "dermatology"

        date_expression = None
        if any(token in normalized for token in ("tomorrow", "بكرة", "غدا", "غداً")):
            date_expression = "tomorrow"
        elif any(token in normalized for token in ("today", "النهاردة", "اليوم")):
            date_expression = "today"

        preferred_time = None
        time_match = re.search(
            r"(?:at\s*|الساعة\s*)?(\d{1,2})(?::([0-5]\d))?\s*(a\.?m\.?|p\.?m\.?|am|pm|صباح(?:اً|ا)?|مساء(?:ً|ا)?)",
            normalized,
        )
        if time_match:
            hour, minute, period = time_match.groups()
            suffix = "PM" if period.startswith(("p", "مسا")) else "AM"
            preferred_time = f"{hour}:{minute} {suffix}" if minute else f"{hour} {suffix}"

        return IntentExtraction(
            intent=Intent.BOOK_APPOINTMENT,
            specialty=specialty,
            date_expression=date_expression,
            preferred_time=preferred_time,
        )