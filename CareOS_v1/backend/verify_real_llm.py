import asyncio
import json
import time
from typing import Literal, Any
from pydantic import BaseModel
from openai import AsyncOpenAI, OpenAIError

from app.config import get_settings
from app.ai.extractor import BookingExtractor
from app.ai.followup.extractor import FollowUpExtractor
from app.ai.booking.agent import BookingAgent
from app.ai.booking.state import build_booking_state
from app.ai.followup.agent import FollowUpAgent
from app.ai.followup.state import build_followup_state


class IntentClassificationContract(BaseModel):
    intent: Literal["booking", "followup", "unknown"]


async def run_real_verification():
    settings = get_settings()

    print("=== CONFIGURATION LOADED FROM .ENV ===")
    print(f"Provider: {settings.ai_provider}")
    print(f"Model: {settings.ai_model}")
    print(f"Base URL: {settings.ai_base_url or settings.ai_api_url or 'DEFAULT'}")
    print(f"API Key Present: {bool(settings.ai_api_key and settings.ai_api_key != 'unconfigured')}")
    print(f"API Key Length: {len(settings.ai_api_key) if settings.ai_api_key else 0}")
    print("======================================\n")

    if not settings.ai_api_key or settings.ai_api_key == "unconfigured":
        print("RESULT: REAL LLM TEST BLOCKED (API key not configured)")
        return

    # Initialize AsyncOpenAI client directly with configured credentials
    base_url = settings.ai_base_url or settings.ai_api_url or None
    client_kwargs: dict[str, Any] = {"api_key": settings.ai_api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = AsyncOpenAI(**client_kwargs)

    prompts = [
        "عايز احجز ميعاد جلدية",
        "عايز أعمل متابعة للمريض بعد أسبوع",
        "عايز أستفسر عن حاجة",
    ]

    print("--- 1. Intent Classification Real LLM Verification ---")
    intent_results = []
    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    latencies = []
    api_reachable = False
    real_requests_executed = False

    for prompt in prompts:
        start_time = time.perf_counter()
        try:
            response = await client.chat.completions.create(
                model=settings.ai_model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Classify the user input into exactly one intent. "
                            "Return JSON with format: {\"intent\": \"booking\" | \"followup\" | \"unknown\"}. "
                            "Use 'booking' when user wants to book/reschedule/cancel an appointment. "
                            "Use 'followup' when user wants to create/manage a follow-up for a patient. "
                            "Otherwise use 'unknown'."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            elapsed = time.perf_counter() - start_time
            latencies.append(elapsed)
            api_reachable = True
            real_requests_executed = True

            content = response.choices[0].message.content or "{}"
            raw_parsed = json.loads(content)
            contract = IntentClassificationContract.model_validate(raw_parsed)

            usage = response.usage
            if usage:
                total_tokens["prompt_tokens"] += getattr(usage, "prompt_tokens", 0)
                total_tokens["completion_tokens"] += getattr(usage, "completion_tokens", 0)
                total_tokens["total_tokens"] += getattr(usage, "total_tokens", 0)

            print(f"Prompt: '{prompt}'")
            print(f"  Result Contract: {contract.model_dump_json()}")
            print(f"  Latency: {elapsed:.3f}s")
            print(f"  Raw Content: {content}")
            if usage:
                print(f"  Tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}")
            print()

            intent_results.append((prompt, contract.intent, elapsed))

        except OpenAIError as exc:
            elapsed = time.perf_counter() - start_time
            print(f"ERROR calling LLM API for prompt '{prompt}': {exc}")
            print("RESULT: REAL LLM TEST BLOCKED (API Call Failed / Unreachable)")
            return
        except Exception as exc:
            print(f"UNEXPECTED ERROR: {exc}")
            print("RESULT: REAL LLM TEST BLOCKED")
            return

    # Check intent accuracy
    # Prompt 1: booking
    # Prompt 2: followup
    # Prompt 3: unknown
    p1_ok = intent_results[0][1] == "booking"
    p2_ok = intent_results[1][1] == "followup"
    p3_ok = intent_results[2][1] == "unknown"
    intent_classification_pass = p1_ok and p2_ok and p3_ok

    print("\n--- 2. REAL LLM -> BookingExtractor -> BookingAgent ---")
    booking_extractor = BookingExtractor(
        api_key=settings.ai_api_key,
        base_url=base_url,
        model=settings.ai_model,
    )
    b_start = time.perf_counter()
    booking_extraction = await booking_extractor.extract("عايز احجز كشف جلدية بكرة الساعة 6 بالليل")
    b_elapsed = time.perf_counter() - b_start

    print(f"Booking Extraction Result: {booking_extraction}")
    booking_state = build_booking_state(booking_extraction, patient_id="test-patient-uuid-1234")
    booking_agent = BookingAgent()
    booking_state = booking_agent.process(booking_state)
    print(f"Booking Agent Processed State status: {booking_state.status}, action: {booking_state.action}, missing_fields: {booking_state.missing_fields}")
    booking_agent_pass = booking_extraction.action == "book" and booking_state.status in {"collecting", "confirming"}

    print("\n--- 3. REAL LLM -> FollowUpExtractor -> FollowUpAgent ---")
    followup_extractor = FollowUpExtractor(
        api_key=settings.ai_api_key,
        base_url=base_url,
        model=settings.ai_model,
    )
    f_start = time.perf_counter()
    followup_extraction = await followup_extractor.extract("عايز أعمل متابعة للمريض مكالمة بكرة الساعة 10 الصبح علشان متابعة الأعراض")
    f_elapsed = time.perf_counter() - f_start

    print(f"FollowUp Extraction Result: {followup_extraction}")
    followup_state = build_followup_state(followup_extraction, patient_id="test-patient-uuid-1234")
    followup_agent = FollowUpAgent()
    followup_state = followup_agent.process(followup_state)
    print(f"FollowUp Agent Processed State status: {followup_state.status}, action: {followup_state.action}, missing_fields: {followup_state.missing_fields}")
    followup_agent_pass = followup_extraction.action == "create" and followup_state.status in {"collecting", "confirming"}

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    print("\n================ FINAL REPORT ================")
    print(f"REAL LLM:")
    print(f"* Provider: {settings.ai_provider}")
    print(f"* Model: {settings.ai_model}")
    print(f"* API reachable: {'YES' if api_reachable else 'NO'}")
    print(f"* Real request executed: {'YES' if real_requests_executed else 'NO'}")
    print(f"* Intent classification: {'PASS' if intent_classification_pass else 'FAIL'}")
    print(f"* BookingAgent interaction: {'PASS' if booking_agent_pass else 'FAIL'}")
    print(f"* FollowUpAgent interaction: {'PASS' if followup_agent_pass else 'FAIL'}")
    print(f"* Average latency: {avg_latency:.3f}s")
    print(f"* Token usage: prompt={total_tokens['prompt_tokens']}, completion={total_tokens['completion_tokens']}, total={total_tokens['total_tokens']}")
    print(f"* Result Nature: REAL (No Mocks/Fallbacks Used)")
    print("==============================================")


if __name__ == "__main__":
    asyncio.run(run_real_verification())
