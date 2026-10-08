"""Multilingual conversation helper for specialized Cosmetics & Aesthetics Clinic."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from voice_agent.app.config import Settings
from voice_agent.app.schemas.requests import ConversationState, Intent

logger = logging.getLogger(__name__)

ARABIC_PATTERN = re.compile(r"[\u0600-\u06FF]")
ACCENT_PATTERN = re.compile(r"[\u00C0-\u024F]")

ARABIC_CLARIFICATIONS = {
    "specialty": "تحب تحجز لأي خدمة أو إجراء تجميلي (زي الفيلر، البوتوكس، الليزر، أو جلسات النضارة والعناية بالبشرة)؟",
    "date": "تمام، تحب تحجز الميعاد يوم إيه؟",
    "preferred_time": "تحب الميعاد الساعة كام؟",
    "appointment_id": "ما هو رقم الموعد الخاص بك؟",
    "emergency": "إذا كنت تعاني من أعراض خطيرة أو حالة طارئة، يرجى الاتصال بالإسعاف (123) فوراً أو التوجه لأقرب قسم طوارئ.",
    "diagnoses_warning": "أنا مساعد استقبال لعيادة التجميل والجلدية التجميلية، ولا يمكنني تقديم تشخيص أو استشارات طبية علاجية. أقدر أساعدك في حجز جلسات وإجراءات التجميل أو الاستفسار عن خدماتنا.",
    "general_prompt": "أهلاً بك في عيادة التجميل! إزاي أقدر أساعد حضرتك اليوم بخصوص خدمات وجلسات التجميل؟",
    "calendar_not_connected": "تم تسجيل تفاصيل طلب ميعاد التجميل لحضرتك، ولكن تقويم العيادة غير متصل حالياً للتأكيد النهائي.",
}

ENGLISH_CLARIFICATIONS = {
    "specialty": "Which cosmetic treatment would you like to book (such as Botox, Fillers, Laser hair removal, or Skin rejuvenation)?",
    "date": "Sure! What day would you like to schedule your appointment for?",
    "preferred_time": "What time would you prefer for your appointment?",
    "appointment_id": "Could you please provide your appointment ID?",
    "emergency": "If you are experiencing a medical emergency, please call emergency services (123 / 911) immediately or proceed to the nearest emergency center.",
    "diagnoses_warning": "I am a reception assistant for the Cosmetics & Aesthetic Clinic. I cannot provide medical diagnoses or prescriptions. I can help you schedule aesthetic procedures or answer questions about our services.",
    "general_prompt": "Welcome to the Cosmetics & Aesthetic Clinic! How can I assist you with our beauty treatments or bookings today?",
    "calendar_not_connected": "Your appointment request has been noted, but the clinic calendar is not currently connected for final confirmation.",
}

ENGLISH_CLINIC_PROMPT = """
You are a friendly, intelligent voice receptionist for a specialized Cosmetics & Aesthetics Clinic.

CRITICAL RULES:
1. CLINIC SPECIALIZATION: Our clinic specializes EXCLUSIVELY in Cosmetics, Aesthetic Dermatology, and Beauty Treatments.
   - Offered services include: Botox & Fillers, Laser Hair Removal & Skin Laser, Skin Rejuvenation & Glow sessions, Chemical Peels, Hydrafacial, Facial Aesthetics, and Body Contouring.
   - We DO NOT have general medical departments such as cardiology, pediatrics, internal medicine, general dentistry, or ophthalmology. If a patient asks about non-cosmetic medical departments, politely clarify that our clinic is dedicated exclusively to cosmetic and aesthetic treatments.
2. OPERATING HOURS: NEVER state, guess, or invent any opening or closing times (such as 9 to 9, etc.). Do NOT give fixed hours. If the patient asks about clinic hours or working times, explain politely that specific working hours and available appointment slots will be checked and provided from the clinic database once they specify their desired visit day or time.
3. STRICT LANGUAGE REQUIREMENT:
   - The patient wrote/spoke in ENGLISH.
   - You MUST reply 100% in natural, fluent, warm ENGLISH only.
   - Do NOT use ANY Arabic characters or Arabic words whatsoever in your answer.
   - Even if the System context contains Arabic text or notes, translate the information and answer purely in English.
4. OUTPUT FORMAT: Structure your response strictly into two parts:
[THOUGHTS]
Brief reasoning in English about cosmetic services and intent.
[ANSWER]
Your concise (1-3 sentences), warm, natural spoken reply strictly in English.
5. MEDICAL SAFETY: Never provide clinical diagnoses or prescriptions. Always recommend scheduling a consultation with our specialized aesthetic physicians.
""".strip()

ARABIC_CLINIC_PROMPT = """
أنت موظف استقبال صوتي ذكي وودود لعيادة تجميل وجلدية تجميلية متخصصة.

قواعد أساسية صارمة:
1. تخصص العيادة: العيادة متخصصة حصرياً في التجميل والجلدية التجميلية وجلسات العناية بالبشرة (فيلر، بوتوكس، ليزر إزالة الشعر، جلسات نضارة، تقشير كيميائي، هيدرافيشل، ونحت القوام). ليس لدينا أي أقسام طبية عامة مثل الباطنة، القلب، العظام، أو الأطفال. إذا استفسر المريض عن تخصصات غير تجميلية، وضح بلباقة أن عيادتنا متخصصة حصرياً في التجميل.
2. مواعيد العمل: لا تذكر أو تخمن أبداً مواعيد فتح أو إغلاق العيادة. وضح بلباقة أن المواعيد الدقيقة وجدول الحجوزات المتاحة يتم مراجعتها وتأكيدها من قاعدة بيانات العيادة بمجرد تحديد اليوم والوقت المفضل للزيارة.
3. مطابقة اللغة (أولوية قصوى):
   - المريض يتحدث بالعربية.
   - يجب أن يكون الرد 100% باللهجة المصرية الدارجة الودودة وبحروف عربية فقط.
   - لا تستخدم أي كلمات إنجليزية في الرد.
4. التنسيق: قسم إجابتك إلى جزأين فقط:
[THOUGHTS]
تفكير موجز عن نية المريض والخدمة التجميلية المطلوبة.
[ANSWER]
ردك الصوتي الودود والمختصر (1-3 جمل) باللهجة المصرية.
5. السلامة الطبية: لا تقدم أي تشخيص طبي أو وصفات علاجية. انصح دائماً بحجز استشارة مع أطبائنا المتخصصين.
""".strip()

COSMETICS_CLINIC_PROMPT = ENGLISH_CLINIC_PROMPT


def is_arabic(text: str) -> bool:
    """Check if the text predominantly contains Arabic characters."""
    arabic_chars = len(ARABIC_PATTERN.findall(text))
    latin_chars = len(re.findall(r"[a-zA-Z]", text))
    if arabic_chars > 0 and latin_chars == 0:
        return True
    return arabic_chars > latin_chars


def contains_any_arabic(text: str) -> bool:
    """Check if the text contains any Arabic characters."""
    return bool(ARABIC_PATTERN.search(text))


def detect_language(text: str, default_lang: str = "en") -> str:
    """Return 'ar' if text is predominantly Arabic, else 'en'."""
    arabic_chars = len(ARABIC_PATTERN.findall(text))
    latin_chars = len(re.findall(r"[a-zA-Z]", text))
    if arabic_chars > latin_chars:
        return "ar"
    if latin_chars > arabic_chars:
        return "en"
    if arabic_chars > 0:
        return "ar"
    if latin_chars > 0:
        return "en"
    return default_lang


def normalize_base_reply_for_language(base_reply: str, target_lang: str) -> str:
    """Ensure base_reply matches the target language before passing to LLM or returning."""
    clean = base_reply.strip()
    if not clean:
        return clean

    if target_lang == "en":
        # Comprehensive conversion of any Arabic system replies to English
        if "تم تأكيد حجز موعد" in clean:
            return clean.replace("تم تأكيد حجز موعد", "Your appointment has been confirmed for").replace("بنجاح. رقم الموعد:", "successfully. Appointment ID:")
        if "الموعد المطلوب غير متاح أو به تعارض" in clean:
            return "The requested appointment slot is not available or has a schedule conflict. Please choose another date or time."
        if "تم تسجيل تفاصيل طلب ميعاد التجميل" in clean:
            return ENGLISH_CLARIFICATIONS["calendar_not_connected"]
        if "لديك" in clean and "مواعيد مسجلة" in clean:
            return "You have scheduled appointments on file."
        if "أنا مساعد استقبال لعيادة التجميل" in clean:
            return ENGLISH_CLARIFICATIONS["diagnoses_warning"]
        if "أهلاً بك في عيادة التجميل" in clean:
            return ENGLISH_CLARIFICATIONS["general_prompt"]
        if "تمت معالجة الطلب بنجاح" in clean:
            return "Your request has been processed successfully by the clinic system."
        if "تحب تحجز لأي خدمة أو إجراء تجميلي" in clean:
            return ENGLISH_CLARIFICATIONS["specialty"]
        if "تحب تحجز الميعاد يوم إيه" in clean:
            return ENGLISH_CLARIFICATIONS["date"]
        if "تحب الميعاد الساعة كام" in clean:
            return ENGLISH_CLARIFICATIONS["preferred_time"]
        if "ما هو رقم الموعد" in clean:
            return ENGLISH_CLARIFICATIONS["appointment_id"]
        if "إذا كنت تعاني من أعراض خطيرة" in clean:
            return ENGLISH_CLARIFICATIONS["emergency"]
        if "تقويم العيادة غير متصل" in clean:
            return ENGLISH_CLARIFICATIONS["calendar_not_connected"]

        # If clean still has any Arabic characters, convert to safe English equivalent
        if contains_any_arabic(clean):
            if any(k in clean for k in ("طوارئ", "إسعاف")):
                return ENGLISH_CLARIFICATIONS["emergency"]
            if any(k in clean for k in ("حجز", "موعد", "ميعاد", "جلسة")):
                return "Your appointment request has been noted, but the clinic calendar is not currently connected for final confirmation."
            return ENGLISH_CLARIFICATIONS["general_prompt"]
        return clean

    if target_lang == "ar":
        lower = clean.lower()
        if "calendar is not connected" in lower or "no booking was made" in lower:
            return ARABIC_CLARIFICATIONS["calendar_not_connected"]
        if "appointment has been confirmed" in lower or "confirmed your booking" in lower:
            return "تم تأكيد حجز موعدك بنجاح في عيادة التجميل."
        if "not available" in lower or "conflict" in lower:
            return "الموعد المطلوب غير متاح أو به تعارض في جدول العيادة، يرجى اختيار موعد آخر."
        if "which medical specialty" in lower or "which cosmetic" in lower:
            return ARABIC_CLARIFICATIONS["specialty"]
        if "what day would you like" in lower:
            return ARABIC_CLARIFICATIONS["date"]
        if "what time would you prefer" in lower:
            return ARABIC_CLARIFICATIONS["preferred_time"]
        if "what is the appointment id" in lower or "provide your appointment id" in lower:
            return ARABIC_CLARIFICATIONS["appointment_id"]
        if "medical emergency" in lower or "emergency services" in lower:
            return ARABIC_CLARIFICATIONS["emergency"]
        if "cannot provide medical diagnoses" in lower or "can't provide diagnoses" in lower:
            return ARABIC_CLARIFICATIONS["diagnoses_warning"]
        if "couldn't reach the healthcare platform" in lower:
            return "تعذر الاتصال بنظام العيادة حالياً. يرجى المحاولة مرة أخرى لاحقاً."
        if "not implemented by the prototype" in lower:
            return "هذه الخدمة غير مفعلة حالياً في النظام التجريبي للعيادة."
        if "having trouble understanding requests" in lower:
            return "أواجه صعوبة مؤقتة في معالجة الطلبات حالياً. يرجى المحاولة بعد قليل."
        if "trouble understanding that request" in lower or "didn't catch that" in lower:
            return "عفواً، لم أتمكن من فهم طلبك بوضوح. ممكن توضح طلبك مرة تانية؟"
        if "you have" in lower and "scheduled appointment" in lower:
            return "لديك مواعيد مسجلة في نظام العيادة."
        if "processed successfully" in lower:
            return "تمت معالجة الطلب بنجاح في نظام العيادة."
        return clean


def build_gemini_prompt(user_text: str, base_reply: str, target_lang: str) -> str:
    """Build a strongly constrained prompt with explicit language enforcement."""
    if target_lang == "en":
        return (
            f"{ENGLISH_CLINIC_PROMPT}\n\n"
            f"LANGUAGE DIRECTIVE: The patient wrote/spoke in ENGLISH.\n"
            f"Your [ANSWER] MUST BE 100% IN NATURAL ENGLISH ONLY.\n"
            f"Do NOT output any Arabic words or Arabic script anywhere in the response.\n\n"
            f"Patient message: {user_text}\n"
            f"System context: {base_reply}"
        )
    return (
        f"{ARABIC_CLINIC_PROMPT}\n\n"
        f"توجيه اللغة: المريض يتحدث بالعربية.\n"
        f"يجب أن يكون [ANSWER] 100% باللهجة المصرية الدارجة وبحروف عربية فقط.\n\n"
        f"رسالة المريض: {user_text}\n"
        f"سياق النظام: {base_reply}"
    )


def parse_thought_and_reply(full_text: str) -> tuple[str | None, str]:
    """Separate thoughts from the spoken reply."""
    if "[ANSWER]" in full_text:
        parts = full_text.rsplit("[ANSWER]", 1)
        thought = parts[0].replace("[THOUGHTS]", "").strip()
        reply = parts[1].strip()
        return thought or None, reply

    thought_match = re.search(r"<thought>(.*?)</thought>", full_text, flags=re.DOTALL)
    if thought_match:
        thought = thought_match.group(1).strip()
        reply = re.sub(r"<thought>.*?</thought>", "", full_text, flags=re.DOTALL).strip()
        return thought, reply

    return None, full_text.strip()


class StreamParser:
    """Stream token parser that separates thoughts and spoken answer."""

    def __init__(self) -> None:
        self.buffer = ""
        self.in_thought = False
        self.past_thought = False

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        events: list[tuple[str, str]] = []
        self.buffer += chunk

        while self.buffer:
            if not self.in_thought and not self.past_thought:
                tag = None
                for candidate in ("[THOUGHTS]", "<thought>"):
                    if candidate in self.buffer:
                        tag = candidate
                        break
                if tag:
                    before, after = self.buffer.split(tag, 1)
                    if before.strip():
                        events.append(("answer", before))
                    self.in_thought = True
                    self.buffer = after
                    continue
                cutoff = None
                for candidate in ("[THOUGHTS]", "<thought>"):
                    for idx in range(1, len(candidate)):
                        if self.buffer.endswith(candidate[:idx]):
                            cutoff = len(self.buffer) - idx
                            break
                    if cutoff is not None:
                        break
                if cutoff is not None:
                    safe = self.buffer[:cutoff]
                    if safe:
                        events.append(("answer", safe))
                    self.buffer = self.buffer[cutoff:]
                    break
                events.append(("answer", self.buffer))
                self.buffer = ""
            elif self.in_thought:
                end_tag = None
                for candidate in ("[ANSWER]", "</thought>"):
                    if candidate in self.buffer:
                        end_tag = candidate
                        break
                if end_tag:
                    before, after = self.buffer.split(end_tag, 1)
                    if before:
                        events.append(("thought", before))
                    self.in_thought = False
                    self.past_thought = True
                    self.buffer = after
                    continue
                cutoff = None
                for candidate in ("[ANSWER]", "</thought>"):
                    for idx in range(1, len(candidate)):
                        if self.buffer.endswith(candidate[:idx]):
                            cutoff = len(self.buffer) - idx
                            break
                    if cutoff is not None:
                        break
                if cutoff is not None:
                    safe = self.buffer[:cutoff]
                    if safe:
                        events.append(("thought", safe))
                    self.buffer = self.buffer[cutoff:]
                    break
                events.append(("thought", self.buffer))
                self.buffer = ""
            else:
                events.append(("answer", self.buffer))
                self.buffer = ""
        return events

    def flush(self) -> list[tuple[str, str]]:
        events: list[tuple[str, str]] = []
        if self.buffer:
            if self.in_thought:
                events.append(("thought", self.buffer))
            else:
                events.append(("answer", self.buffer))
            self.buffer = ""
        return events


async def generate_multilingual_reply(
    user_text: str,
    base_reply: str,
    state: ConversationState,
    settings: Settings,
    *,
    client_factory: Any | None = None,
) -> tuple[str | None, str]:
    """Provide structured thinking and spoken response matching the patient's language."""
    clean_text = user_text.strip()
    if not clean_text:
        return None, base_reply

    target_lang = detect_language(clean_text)
    clarifications = ARABIC_CLARIFICATIONS if target_lang == "ar" else ENGLISH_CLARIFICATIONS
    normalized_base = normalize_base_reply_for_language(base_reply, target_lang)

    # 1. Deterministic Emergency Route
    if state.current_intent == Intent.EMERGENCY:
        thought = (
            "حالة طوارئ طبية: توجيه المريض إلى الإسعاف فوراً."
            if target_lang == "ar"
            else "Medical emergency: directing patient to emergency services immediately."
        )
        return thought, clarifications["emergency"]

    # 2. Slot-Filling (Missing Parameters)
    is_question = any(
        q in clean_text.lower()
        for q in [
            "what", "how", "when", "where", "why", "who", "cost", "price",
            "كام", "فين", "إيه", "ايه", "ازاي", "إزاي", "مين", "هل", "مكان", "عنوان", "ساعة", "مواعيد", "تفتح", "?", "؟"
        ]
    )
    if (
        state.missing_parameters
        and state.current_intent in {
            Intent.BOOK_APPOINTMENT,
            Intent.CANCEL_APPOINTMENT,
            Intent.RESCHEDULE_APPOINTMENT,
        }
        and not is_question
    ):
        missing_key = state.missing_parameters[0]
        if missing_key in clarifications:
            thought = (
                f"طلب حجز أو تعديل موعد تجميل. جارٍ طلب المعامل المفقود: {missing_key}."
                if target_lang == "ar"
                else f"Cosmetic booking/modification request. Inquiring for missing detail: {missing_key}."
            )
            return thought, clarifications[missing_key]

    # 3. Calendar Not Connected
    if "calendar is not connected" in base_reply.lower() or "no booking was made" in base_reply.lower() or "تقويم العيادة غير متصل" in base_reply:
        thought = (
            "طلب حجز موعد تجميل. تقويم العيادة غير متصل بقاعدة البيانات للتأكيد النهائي."
            if target_lang == "ar"
            else "Cosmetics booking request. Clinic calendar is not connected to database for final confirmation."
        )
        return thought, clarifications["calendar_not_connected"]

    # 4. LLM Generation
    if settings.llm_provider.casefold() == "gemini" and settings.llm_api_key:
        reply = await _ask_gemini_assistant(user_text, normalized_base, target_lang, settings, client_factory=client_factory)
        if reply:
            thought, answer = parse_thought_and_reply(reply)
            # Enforce language consistency strictly
            if target_lang == "en" and contains_any_arabic(answer):
                logger.warning("Language mismatch detected in LLM answer (Arabic on English prompt). Correcting to English.")
                answer = normalized_base
            elif target_lang == "ar" and not contains_any_arabic(answer):
                logger.warning("Language mismatch detected in LLM answer (English on Arabic prompt). Correcting to Arabic.")
                answer = normalized_base
            return thought, answer

    # 5. Fallback Responses
    if state.current_intent == Intent.GENERAL_QUESTION:
        thought = "استفسار عن خدمات عيادة التجميل." if target_lang == "ar" else "Inquiry regarding cosmetics services."
        return thought, clarifications["diagnoses_warning"]

    thought = (
        f"طلب خاص بعيادة التجميل ({state.current_intent.value if state.current_intent else 'عام'})."
        if target_lang == "ar"
        else f"Cosmetics Clinic request ({state.current_intent.value if state.current_intent else 'general'})."
    )
    return thought, normalized_base


async def stream_multilingual_reply(
    user_text: str,
    base_reply: str,
    state: ConversationState,
    settings: Settings,
    *,
    client_factory: Any | None = None,
) -> AsyncIterator[tuple[str, str]]:
    """Stream token chunks of ('thought', text) and ('answer', text) strictly matching user language."""
    clean_text = user_text.strip()
    if not clean_text:
        yield ("answer", base_reply)
        return

    target_lang = detect_language(clean_text)
    clarifications = ARABIC_CLARIFICATIONS if target_lang == "ar" else ENGLISH_CLARIFICATIONS
    normalized_base = normalize_base_reply_for_language(base_reply, target_lang)

    # 1. Deterministic Emergency Route
    if state.current_intent == Intent.EMERGENCY:
        thought = (
            "حالة طوارئ طبية: توجيه المريض إلى الإسعاف فوراً."
            if target_lang == "ar"
            else "Medical emergency: directing patient to emergency services immediately."
        )
        yield ("thought", thought)
        yield ("answer", clarifications["emergency"])
        return

    # 2. Slot-Filling (Missing Parameters)
    is_question = any(
        q in clean_text.lower()
        for q in [
            "what", "how", "when", "where", "why", "who", "cost", "price",
            "كام", "فين", "إيه", "ايه", "ازاي", "إزاي", "مين", "هل", "مكان", "عنوان", "ساعة", "مواعيد", "تفتح", "?", "؟"
        ]
    )
    if (
        state.missing_parameters
        and state.current_intent in {
            Intent.BOOK_APPOINTMENT,
            Intent.CANCEL_APPOINTMENT,
            Intent.RESCHEDULE_APPOINTMENT,
        }
        and not is_question
    ):
        missing_key = state.missing_parameters[0]
        if missing_key in clarifications:
            thought = (
                f"طلب حجز أو تعديل موعد تجميل. جارٍ طلب المعامل المفقود: {missing_key}."
                if target_lang == "ar"
                else f"Cosmetic booking/modification request. Inquiring for missing detail: {missing_key}."
            )
            yield ("thought", thought)
            yield ("answer", clarifications[missing_key])
            return

    # 3. Calendar Not Connected
    if "calendar is not connected" in base_reply.lower() or "no booking was made" in base_reply.lower() or "تقويم العيادة غير متصل" in base_reply:
        thought = (
            "طلب حجز موعد تجميل. تقويم العيادة غير متصل بقاعدة البيانات للتأكيد النهائي."
            if target_lang == "ar"
            else "Cosmetics booking request. Clinic calendar is not connected to database for final confirmation."
        )
        yield ("thought", thought)
        yield ("answer", clarifications["calendar_not_connected"])
        return

    # 4. Use Gemini Stream if Enabled
    if settings.llm_provider.casefold() == "gemini" and settings.llm_api_key:
        parser = StreamParser()
        streamed_any = False
        accumulated_answer = ""
        has_language_mismatch = False
        buffered_events: list[tuple[str, str]] = []
        try:
            if client_factory is not None:
                client = client_factory(api_key=settings.llm_api_key)
            else:
                from google import genai

                client = genai.Client(api_key=settings.llm_api_key)

            full_prompt = build_gemini_prompt(user_text, normalized_base, target_lang)
            response = await client.aio.models.generate_content_stream(
                model=settings.llm_model or "gemini-3.5-flash-lite",
                contents=full_prompt,
            )
            async for chunk in response:
                if chunk.text:
                    for event_type, text in parser.feed(chunk.text):
                        streamed_any = True
                        if event_type == "answer":
                            accumulated_answer += text
                            if target_lang == "en" and contains_any_arabic(text):
                                has_language_mismatch = True
                            elif target_lang == "ar" and not contains_any_arabic(text) and len(re.findall(r"[a-zA-Z]", text)) > 3:
                                has_language_mismatch = True

                        if not has_language_mismatch:
                            yield (event_type, text)
                        else:
                            buffered_events.append((event_type, text))

            for event_type, text in parser.flush():
                streamed_any = True
                if event_type == "answer":
                    accumulated_answer += text
                    if target_lang == "en" and contains_any_arabic(text):
                        has_language_mismatch = True
                    elif target_lang == "ar" and not contains_any_arabic(text) and len(re.findall(r"[a-zA-Z]", text)) > 3:
                        has_language_mismatch = True

                if not has_language_mismatch:
                    yield (event_type, text)
                else:
                    buffered_events.append((event_type, text))

        except Exception as exc:
            logger.warning("multilingual.gemini_stream.failed (%s: %s)", type(exc).__name__, exc)

        if streamed_any:
            if has_language_mismatch or (target_lang == "en" and contains_any_arabic(accumulated_answer)):
                logger.warning("Language mismatch detected in stream. Emitting normalized reply.")
                yield ("answer", normalized_base)
            return

    # 5. Deterministic / Fallback response
    thought, reply = await generate_multilingual_reply(
        user_text, normalized_base, state, settings, client_factory=client_factory
    )
    if thought:
        yield ("thought", thought)
    yield ("answer", reply)


async def _ask_gemini_assistant(
    user_text: str,
    base_reply: str,
    target_lang: str,
    settings: Settings,
    *,
    client_factory: Any | None = None,
) -> str | None:
    try:
        if client_factory is not None:
            client = client_factory(api_key=settings.llm_api_key)
        else:
            from google import genai

            client = genai.Client(api_key=settings.llm_api_key)

        prompt = build_gemini_prompt(user_text, base_reply, target_lang)
        response = await client.aio.models.generate_content(
            model=settings.llm_model or "gemini-3.5-flash-lite",
            contents=prompt,
        )
        if response.text and response.text.strip():
            return response.text.strip()
    except Exception as exc:
        logger.warning("multilingual.gemini_assistant.failed (%s)", type(exc).__name__)

    return None
