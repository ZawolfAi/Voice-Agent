"""Tests ensuring strict language matching: English prompts get 100% English replies,

Arabic prompts get 100% Egyptian Arabic replies, with zero cross-contamination.
"""

from __future__ import annotations

import pytest

from voice_agent.app.agent.multilingual import (
    contains_any_arabic,
    detect_language,
    generate_multilingual_reply,
    is_arabic,
    normalize_base_reply_for_language,
    stream_multilingual_reply,
)
from voice_agent.app.config import Settings
from voice_agent.app.schemas.requests import ConversationState, Intent


def test_detect_language_precision() -> None:
    # Pure English
    assert detect_language("Hello, I need an appointment for Botox") == "en"
    assert detect_language("What are your opening hours?") == "en"
    assert detect_language("Do you do laser hair removal?") == "en"

    # Mixed English with minor Arabic keyword/brand
    assert detect_language("I want a botox session (بوتوكس)") == "en"
    assert detect_language("Is Dr. Sara at the clinic? شكرا") == "en"

    # Pure Arabic
    assert detect_language("عايز أحجز ميعاد للبوتوكس بكرة") == "ar"
    assert detect_language("العيادة بتفتح الساعة كام؟") == "ar"
    assert detect_language("بكام جلسة الفيلر؟") == "ar"

    # Numbers and symbols preserve default/fallback
    assert detect_language("5:00 PM", default_lang="en") == "en"
    assert detect_language("123", default_lang="ar") == "ar"
    assert detect_language("123", default_lang="en") == "en"


def test_normalize_base_reply_never_leaks_arabic_to_english() -> None:
    arabic_samples = [
        "تم تأكيد حجز موعد Botox بنجاح. رقم الموعد: 101.",
        "الموعد المطلوب غير متاح أو به تعارض في جدول العيادة",
        "تم تسجيل تفاصيل طلب ميعاد التجميل لحضرتك، ولكن تقويم العيادة غير متصل حالياً للتأكيد النهائي.",
        "لديك 3 مواعيد مسجلة في نظام العيادة.",
        "أنا مساعد استقبال لعيادة التجميل والجلدية التجميلية",
        "أهلاً بك في عيادة التجميل! إزاي أقدر أساعد حضرتك اليوم؟",
        "تمت معالجة الطلب بنجاح في نظام العيادة.",
        "إذا كنت تعاني من أعراض خطيرة أو حالة طارئة، يرجى الاتصال بالإسعاف (123) فوراً",
        "تحب تحجز لأي خدمة أو إجراء تجميلي (زي الفيلر، البوتوكس، الليزر)؟",
        "تمام، تحب تحجز الميعاد يوم إيه؟",
        "تحب الميعاد الساعة كام؟",
        "ما هو رقم الموعد الخاص بك؟",
    ]
    for sample in arabic_samples:
        normalized = normalize_base_reply_for_language(sample, target_lang="en")
        assert not contains_any_arabic(normalized), f"Arabic leaked to English for '{sample}': '{normalized}'"
        assert len(normalized) > 0


def test_normalize_base_reply_converts_english_to_arabic() -> None:
    english_samples = [
        "Which medical specialty would you prefer?",
        "Sure. What day would you like to book the appointment?",
        "What time would you prefer?",
        "What is the appointment ID you would like me to use?",
        "The clinic calendar is not connected, so I can't verify real availability.",
        "I can't provide diagnoses or treatment advice.",
    ]
    for sample in english_samples:
        normalized = normalize_base_reply_for_language(sample, target_lang="ar")
        assert contains_any_arabic(normalized), f"Failed to convert '{sample}' to Arabic: '{normalized}'"


@pytest.mark.asyncio
async def test_generate_multilingual_reply_strictly_english() -> None:
    settings = Settings(llm_provider="demo")
    state = ConversationState()
    state.current_intent = Intent.BOOK_APPOINTMENT
    state.missing_parameters = ["specialty", "date", "preferred_time"]

    # Slot-filling question for English prompt must be 100% English
    thought, answer = await generate_multilingual_reply(
        "I want to book an appointment",
        "Which cosmetic treatment would you prefer?",
        state,
        settings,
    )
    assert not contains_any_arabic(answer), f"Answer contained Arabic: {answer}"
    assert "cosmetic" in answer.lower() or "treatment" in answer.lower()

    # Slot-filling question for Arabic prompt must be 100% Arabic
    thought_ar, answer_ar = await generate_multilingual_reply(
        "عاوز أحجز ميعاد",
        "تحب تحجز لأي خدمة أو إجراء تجميلي؟",
        state,
        settings,
    )
    assert contains_any_arabic(answer_ar), f"Answer was not Arabic: {answer_ar}"


@pytest.mark.asyncio
async def test_generate_multilingual_reply_intercepts_corrupted_llm_output() -> None:
    settings = Settings(llm_provider="gemini", llm_api_key="mock-key")
    state = ConversationState()
    state.current_intent = Intent.GENERAL_QUESTION

    # Mock client factory that returns an Arabic answer to an English prompt
    class FakeCorruptedModel:
        async def generate_content(self, model: str, contents: str):
            class Resp:
                text = "[THOUGHTS]\nThinking in English\n[ANSWER]\nأهلاً بك في عيادة التجميل نحن نقدم خدمات ممتازة"
            return Resp()

    class FakeClient:
        aio = type("AIO", (), {"models": FakeCorruptedModel()})()

    thought, answer = await generate_multilingual_reply(
        "What services do you offer?",
        "Welcome to the Cosmetics & Aesthetic Clinic! How can I assist you with our beauty treatments or bookings today?",
        state,
        settings,
        client_factory=lambda api_key: FakeClient(),
    )
    # The corrupted Arabic answer MUST be intercepted and sanitized to English
    assert not contains_any_arabic(answer), f"Arabic response was not intercepted: {answer}"
    assert "Cosmetics" in answer or "treatment" in answer or "Welcome" in answer


@pytest.mark.asyncio
async def test_stream_multilingual_reply_strictly_english() -> None:
    settings = Settings(llm_provider="demo")
    state = ConversationState()
    state.current_intent = Intent.BOOK_APPOINTMENT
    state.missing_parameters = ["date"]

    events = []
    async for event_type, chunk in stream_multilingual_reply(
        "I want to book Botox",
        "Sure. What day would you like to book the appointment?",
        state,
        settings,
    ):
        events.append((event_type, chunk))

    answer_text = "".join(chunk for evt, chunk in events if evt == "answer")
    assert not contains_any_arabic(answer_text), f"Streamed answer contained Arabic: {answer_text}"
    assert "day" in answer_text.lower() or "schedule" in answer_text.lower()
