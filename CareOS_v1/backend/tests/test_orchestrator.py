from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from openai import OpenAIError

from app.ai.booking.agent import BookingAgent
from app.ai.booking.contracts import BookingExtraction
from app.ai.extractor import BookingExtractor
from app.ai.followup.agent import FollowUpAgent
from app.ai.followup.contracts import FollowUpExtraction
from app.ai.followup.extractor import FollowUpExtractor
from app.ai.orchestrator import (
    CareOSOrchestrator,
    IntentResult,
    IntentRouter,
    IntentType,
    OrchestratorState,
)
from app.config import get_settings
from app.db import init_db, session_factory
from app.models import Appointment, FollowUp, Organization, Patient, User
from app.ai.booking.tools import BookingTools
from app.ai.followup.tools import FollowUpTools

_schema_initialized = False


async def _ensure_test_schema() -> None:
    global _schema_initialized
    if not _schema_initialized:
        await init_db()
        _schema_initialized = True


async def _make_user_and_patient() -> tuple[User, Patient]:
    await _ensure_test_schema()
    async with session_factory() as session:
        organization = Organization(name=f"Orch Test Org {uuid4().hex[:6]}")
        session.add(organization)
        await session.flush()
        user = User(
            organization_id=organization.id,
            email=f"orch-test-{uuid4().hex[:8]}@example.org",
            full_name="Orchestrator Test User",
            role="admin",
            password_hash="test-password-hash",
            onboarding_complete=True,
        )
        patient = Patient(
            organization_id=organization.id,
            medical_record_number=f"ORCH-PAT-{uuid4().hex[:8]}",
            given_name="Orchestrator",
            family_name="Patient",
            date_of_birth=date(1995, 3, 20),
        )
        session.add_all([user, patient])
        await session.commit()
        return user, patient


# ============================================================================
# 1. IntentRouter Unit Tests (Mocked LLM)
# ============================================================================


@pytest.mark.asyncio
async def test_router_arabic_booking_intent() -> None:
    """Test 1: Arabic booking request classifies as IntentType.BOOKING."""
    router = IntentRouter(api_key="test-key")
    mock_resp = AsyncMock()
    mock_resp.choices = [AsyncMock(message=AsyncMock(content='{"intent": "booking"}'))]

    with patch.object(router.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp):
        res = await router.classify("عايز احجز ميعاد جلدية")
        assert res.intent == IntentType.BOOKING


@pytest.mark.asyncio
async def test_router_arabic_followup_intent() -> None:
    """Test 2: Arabic follow-up request classifies as IntentType.FOLLOWUP."""
    router = IntentRouter(api_key="test-key")
    mock_resp = AsyncMock()
    mock_resp.choices = [AsyncMock(message=AsyncMock(content='{"intent": "followup"}'))]

    with patch.object(router.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp):
        res = await router.classify("عايز أعمل متابعة للمريض بعد أسبوع")
        assert res.intent == IntentType.FOLLOWUP


@pytest.mark.asyncio
async def test_router_unknown_request_intent() -> None:
    """Test 3: General inquiry request classifies as IntentType.UNKNOWN."""
    router = IntentRouter(api_key="test-key")
    mock_resp = AsyncMock()
    mock_resp.choices = [AsyncMock(message=AsyncMock(content='{"intent": "unknown"}'))]

    with patch.object(router.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp):
        res = await router.classify("عايز أستفسر عن حاجة")
        assert res.intent == IntentType.UNKNOWN


@pytest.mark.asyncio
async def test_router_malformed_llm_json_fallback() -> None:
    """Test 4: Malformed LLM JSON response defaults safely to IntentType.UNKNOWN."""
    router = IntentRouter(api_key="test-key")
    mock_resp = AsyncMock()
    mock_resp.choices = [AsyncMock(message=AsyncMock(content="Invalid Non-JSON output"))]

    with patch.object(router.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp):
        res = await router.classify("عايز احجز")
        assert res.intent == IntentType.UNKNOWN


@pytest.mark.asyncio
async def test_router_invalid_intent_string_fallback() -> None:
    """Test 5: Unrecognized intent string from LLM defaults to IntentType.UNKNOWN."""
    router = IntentRouter(api_key="test-key")
    mock_resp = AsyncMock()
    mock_resp.choices = [AsyncMock(message=AsyncMock(content='{"intent": "random_unsupported_intent"}'))]

    with patch.object(router.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp):
        res = await router.classify("عايز احجز")
        assert res.intent == IntentType.UNKNOWN


@pytest.mark.asyncio
async def test_router_llm_api_error_fallback() -> None:
    """Test 6: OpenAI API exception defaults safely to IntentType.UNKNOWN."""
    router = IntentRouter(api_key="test-key")

    with patch.object(router.client.chat.completions, "create", side_effect=OpenAIError("API Timeout")):
        res = await router.classify("عايز احجز ميعاد")
        assert res.intent == IntentType.UNKNOWN


# ============================================================================
# 2. Orchestrator Logic Tests (Routing & Agents Isolation)
# ============================================================================


@pytest.mark.asyncio
async def test_orchestrator_booking_routes_only_to_booking_agent() -> None:
    """Test 7: Booking intent routes ONLY to BookingAgent, NOT FollowUpAgent."""
    router = AsyncMock(spec=IntentRouter)
    router.classify.return_value = IntentResult(intent=IntentType.BOOKING)

    booking_extractor = AsyncMock(spec=BookingExtractor)
    booking_extractor.extract.return_value = BookingExtraction(action="book", specialty="dermatology", date="tomorrow", time="18:00")

    followup_extractor = AsyncMock(spec=FollowUpExtractor)
    booking_agent = BookingAgent()
    followup_agent = FollowUpAgent()

    orchestrator = CareOSOrchestrator(
        router=router,
        booking_extractor=booking_extractor,
        followup_extractor=followup_extractor,
        booking_agent=booking_agent,
        followup_agent=followup_agent,
    )

    response = await orchestrator.process("عايز احجز ميعاد جلدية", patient_id=str(uuid4()))

    assert response.intent == IntentType.BOOKING
    assert response.booking_agent_called is True
    assert response.followup_agent_called is False
    assert followup_extractor.extract.call_count == 0


@pytest.mark.asyncio
async def test_orchestrator_followup_routes_only_to_followup_agent() -> None:
    """Test 8: Followup intent routes ONLY to FollowUpAgent, NOT BookingAgent."""
    router = AsyncMock(spec=IntentRouter)
    router.classify.return_value = IntentResult(intent=IntentType.FOLLOWUP)

    booking_extractor = AsyncMock(spec=BookingExtractor)
    followup_extractor = AsyncMock(spec=FollowUpExtractor)
    followup_extractor.extract.return_value = FollowUpExtraction(action="create", followup_type="call", date="tomorrow", time="10:00")

    booking_agent = BookingAgent()
    followup_agent = FollowUpAgent()

    orchestrator = CareOSOrchestrator(
        router=router,
        booking_extractor=booking_extractor,
        followup_extractor=followup_extractor,
        booking_agent=booking_agent,
        followup_agent=followup_agent,
    )

    response = await orchestrator.process("عايز أعمل متابعة للمريض بعد أسبوع", patient_id=str(uuid4()))

    assert response.intent == IntentType.FOLLOWUP
    assert response.followup_agent_called is True
    assert response.booking_agent_called is False
    assert booking_extractor.extract.call_count == 0


@pytest.mark.asyncio
async def test_orchestrator_unknown_routes_to_clarification() -> None:
    """Test 9: Unknown intent returns clarification without calling either agent."""
    router = AsyncMock(spec=IntentRouter)
    router.classify.return_value = IntentResult(intent=IntentType.UNKNOWN)

    booking_extractor = AsyncMock(spec=BookingExtractor)
    followup_extractor = AsyncMock(spec=FollowUpExtractor)

    orchestrator = CareOSOrchestrator(
        router=router,
        booking_extractor=booking_extractor,
        followup_extractor=followup_extractor,
    )

    response = await orchestrator.process("عايز أستفسر عن حاجة")

    assert response.intent == IntentType.UNKNOWN
    assert response.status == "clarification"
    assert "I need a little more information" in response.message
    assert response.booking_agent_called is False
    assert response.followup_agent_called is False
    assert booking_extractor.extract.call_count == 0
    assert followup_extractor.extract.call_count == 0


@pytest.mark.asyncio
async def test_orchestrator_multi_turn_conversation_continuity() -> None:
    """Test 10 & 11: Multi-turn conversation preserves active agent state."""
    router = AsyncMock(spec=IntentRouter)

    booking_extractor = AsyncMock(spec=BookingExtractor)
    # Turn 1: user asks to book
    booking_extractor.extract.side_effect = [
        BookingExtraction(action="book", specialty="dermatology"),
        BookingExtraction(action="book", specialty="dermatology", date="tomorrow", time="18:00", reason="Skin rash"),
    ]

    router.classify.side_effect = [
        IntentResult(intent=IntentType.BOOKING),
        IntentResult(intent=IntentType.BOOKING),
    ]

    orchestrator = CareOSOrchestrator(
        router=router,
        booking_extractor=booking_extractor,
    )

    pid = str(uuid4())
    # Turn 1
    resp1 = await orchestrator.process("عايز احجز جلدية", patient_id=pid)
    assert resp1.intent == IntentType.BOOKING
    assert resp1.status == "collecting"
    state1 = resp1.orchestrator_state

    # Turn 2: user provides date/time and reason
    resp2 = await orchestrator.process("بكرة الساعة 6 بالليل علشان حساسية", state=state1)
    assert resp2.intent == IntentType.BOOKING
    assert resp2.status == "confirming"


# ============================================================================
# 3. REAL GROQ LLM INTEGRATION TESTS (NO MOCKS ALLOWED)
# ============================================================================


@pytest.mark.asyncio
async def test_real_llm_intent_router_classification() -> None:
    """Test 13 (REAL): Verify REAL Groq LLM classifies user intent correctly."""
    settings = get_settings()
    if not settings.ai_api_key or settings.ai_api_key == "unconfigured":
        pytest.skip("REAL LLM TEST SKIPPED (API Key unconfigured)")

    router = IntentRouter()
    r1 = await router.classify("عايز احجز ميعاد جلدية")
    assert r1.intent == IntentType.BOOKING

    r2 = await router.classify("عايز أعمل متابعة للمريض بعد أسبوع")
    assert r2.intent == IntentType.FOLLOWUP

    r3 = await router.classify("عايز أستفسر عن حاجة")
    assert r3.intent == IntentType.UNKNOWN


@pytest.mark.asyncio
async def test_real_llm_orchestrator_e2e_booking_pipeline() -> None:
    """Test 14 (REAL): Verify REAL Groq LLM -> Orchestrator -> BookingAgent -> BookingTools -> Database persistence."""
    settings = get_settings()
    if not settings.ai_api_key or settings.ai_api_key == "unconfigured":
        pytest.skip("REAL LLM TEST SKIPPED (API Key unconfigured)")

    user, patient = await _make_user_and_patient()
    orchestrator = CareOSOrchestrator()

    # Step 1: User message to book appointment
    resp1 = await orchestrator.process(
        "عايز احجز كشف جلدية بكرة الساعة 6 بالليل علشان حساسية في الجلد",
        patient_id=str(patient.id),
    )

    assert resp1.intent == IntentType.BOOKING
    assert resp1.booking_agent_called is True
    assert resp1.followup_agent_called is False
    assert resp1.status in {"collecting", "confirming"}

    # Step 2: Confirm operation and execute tools against real DB
    state = resp1.orchestrator_state
    async with session_factory() as session:
        booking_tools = BookingTools(session=session, user=user)
        # Execute confirmation turn
        resp2 = await orchestrator.process(
            "موافق تأكيد الحجز",
            state=state,
            booking_tools=booking_tools,
        )

        assert resp2.intent == IntentType.BOOKING
        assert resp2.status == "completed"
        assert resp2.result is not None
        appointment_id = resp2.result["id"]

        # Step 3: Direct DB check
        db_appt = await session.get(Appointment, appointment_id)
        assert db_appt is not None
        assert db_appt.patient_id == patient.id
        assert db_appt.organization_id == user.organization_id
        assert db_appt.status == "confirmed"


@pytest.mark.asyncio
async def test_real_llm_orchestrator_e2e_followup_pipeline() -> None:
    """Test 15 (REAL): Verify REAL Groq LLM -> Orchestrator -> FollowUpAgent -> FollowUpTools -> Database persistence."""
    settings = get_settings()
    if not settings.ai_api_key or settings.ai_api_key == "unconfigured":
        pytest.skip("REAL LLM TEST SKIPPED (API Key unconfigured)")

    user, patient = await _make_user_and_patient()
    orchestrator = CareOSOrchestrator()

    # Step 1: User message for follow-up
    resp1 = await orchestrator.process(
        "عايز أعمل متابعة للمريض مكالمة بكرة الساعة 10 الصبح علشان متابعة الأعراض",
        patient_id=str(patient.id),
    )

    assert resp1.intent == IntentType.FOLLOWUP
    assert resp1.followup_agent_called is True
    assert resp1.booking_agent_called is False
    assert resp1.status == "confirming"

    # Step 2: Confirm and execute tools against real DB
    state = resp1.orchestrator_state
    async with session_factory() as session:
        followup_tools = FollowUpTools(session=session, user=user)
        resp2 = await orchestrator.process(
            "موافق تأكيد المتابعة",
            state=state,
            followup_tools=followup_tools,
        )

        assert resp2.intent == IntentType.FOLLOWUP
        assert resp2.status == "completed"
        assert resp2.result is not None
        followup_id = resp2.result["id"]

        # Step 3: Direct DB check
        db_followup = await session.get(FollowUp, followup_id)
        assert db_followup is not None
        assert db_followup.patient_id == patient.id
        assert db_followup.organization_id == user.organization_id
        assert db_followup.followup_type == "call"
        assert db_followup.status == "pending"
