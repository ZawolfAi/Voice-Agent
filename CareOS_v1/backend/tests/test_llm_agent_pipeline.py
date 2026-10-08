from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from openai import OpenAIError
from sqlalchemy import select

from app.ai.booking.agent import BookingAgent
from app.ai.booking.contracts import BookingExtraction
from app.ai.booking.state import build_booking_state
from app.ai.booking.tools import BookingTools
from app.ai.extractor import BookingExtractor, GroqExtractor
from app.ai.followup.agent import FollowUpAgent
from app.ai.followup.contracts import FollowUpExtraction
from app.ai.followup.extractor import FollowUpExtractor
from app.ai.followup.state import build_followup_state
from app.ai.followup.tools import FollowUpTools
from app.db import init_db, session_factory
from app.models import Appointment, FollowUp, Organization, Patient, User

_schema_initialized = False


async def _ensure_test_schema() -> None:
    global _schema_initialized
    if not _schema_initialized:
        await init_db()
        _schema_initialized = True


async def _make_user_and_patient() -> tuple[User, Patient]:
    await _ensure_test_schema()
    async with session_factory() as session:
        organization = Organization(name=f"LLM Test Org {uuid4().hex[:6]}")
        session.add(organization)
        await session.flush()
        user = User(
            organization_id=organization.id,
            email=f"llm-test-{uuid4().hex[:8]}@example.org",
            full_name="LLM Test User",
            role="admin",
            password_hash="test-password-hash",
            onboarding_complete=True,
        )
        patient = Patient(
            organization_id=organization.id,
            medical_record_number=f"LLM-PAT-{uuid4().hex[:8]}",
            given_name="LLM",
            family_name="Patient",
            date_of_birth=date(1992, 5, 15),
        )
        session.add_all([user, patient])
        await session.commit()
        return user, patient


# ============================================================================
# 1. Structured Extractor Tests (English & Arabic)
# ============================================================================


@pytest.mark.asyncio
async def test_booking_extractor_structured_parsing_english_and_arabic() -> None:
    """Verify BookingExtractor correctly parses English & Arabic LLM JSON responses into Pydantic models."""
    extractor = BookingExtractor(api_key="test-key")

    mock_en_response = AsyncMock()
    mock_en_response.choices = [
        AsyncMock(
            message=AsyncMock(
                content='{"action": "book", "confirmation": "unknown", "specialty": "cardiology", "date": "tomorrow", "time": "10:00", "appointment_id": null, "reason": "Heart checkup"}'
            )
        )
    ]

    with patch.object(extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_en_response):
        result_en = await extractor.extract("I want to book a cardiology appointment tomorrow at 10:00 for Heart checkup")
        assert isinstance(result_en, BookingExtraction)
        assert result_en.action == "book"
        assert result_en.specialty == "cardiology"
        assert result_en.date == "tomorrow"
        assert result_en.time == "10:00"
        assert result_en.reason == "Heart checkup"

    mock_ar_response = AsyncMock()
    mock_ar_response.choices = [
        AsyncMock(
            message=AsyncMock(
                content='{"action": "book", "confirmation": "unknown", "specialty": "dermatology", "date": "tomorrow", "time": "18:00", "appointment_id": null, "reason": "كشف جلدية"}'
            )
        )
    ]

    with patch.object(extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_ar_response):
        result_ar = await extractor.extract("عايز احجز كشف جلدية بكرة الساعة 6 بالليل")
        assert isinstance(result_ar, BookingExtraction)
        assert result_ar.action == "book"
        assert result_ar.specialty == "dermatology"
        assert result_ar.date == "tomorrow"
        assert result_ar.time == "18:00"


@pytest.mark.asyncio
async def test_followup_extractor_structured_parsing_english_and_arabic() -> None:
    """Verify FollowUpExtractor correctly parses English & Arabic LLM JSON responses into Pydantic models."""
    extractor = FollowUpExtractor(api_key="test-key")

    mock_ar_response = AsyncMock()
    mock_ar_response.choices = [
        AsyncMock(
            message=AsyncMock(
                content='{"action": "create", "confirmation": "unknown", "followup_type": "call", "date": "tomorrow", "time": "10:00", "appointment_id": null, "followup_id": null, "reason": "متابعة الأعراض"}'
            )
        )
    ]

    with patch.object(extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_ar_response):
        result_ar = await extractor.extract("عايز أعمل متابعة للمريض مكالمة بكرة الساعة 10 الصبح علشان متابعة الأعراض")
        assert isinstance(result_ar, FollowUpExtraction)
        assert result_ar.action == "create"
        assert result_ar.followup_type == "call"
        assert result_ar.date == "tomorrow"
        assert result_ar.time == "10:00"
        assert result_ar.reason == "متابعة الأعراض"


# ============================================================================
# 2. End-to-End Pipeline Tests: User Message -> LLM -> Agent -> Service -> DB
# ============================================================================


@pytest.mark.asyncio
async def test_e2e_booking_pipeline_user_message_to_db() -> None:
    """
    Test End-to-End Pipeline for Booking:
    User Message -> LLM Extractor -> BookingExtraction -> BookingState -> BookingAgent -> BookingTools -> Database
    """
    user, patient = await _make_user_and_patient()
    extractor = BookingExtractor(api_key="test-key")

    mock_response = AsyncMock()
    mock_response.choices = [
        AsyncMock(
            message=AsyncMock(
                content='{"action": "book", "confirmation": "unknown", "specialty": "cardiology", "date": "tomorrow", "time": "10:00", "appointment_id": null, "reason": "Routine Checkup"}'
            )
        )
    ]

    fixed_now = datetime(2026, 10, 10, 8, 0, 0, tzinfo=timezone.utc)

    # Step 1: User message -> LLM Extractor
    with patch.object(extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
        extraction = await extractor.extract("Book a cardiology appointment for tomorrow at 10:00 for Routine Checkup")

    # Step 2: Build state from extraction
    state = build_booking_state(
        extraction,
        patient_id=str(patient.id),
        timezone="UTC",
        now=fixed_now,
    )
    assert state.action == "book"
    assert state.specialty == "cardiology"
    assert state.starts_at == datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)

    # Step 3: Agent process (evaluates fields & transitions status to confirming)
    agent = BookingAgent()
    state = agent.process(state)
    assert state.status == "confirming"
    assert state.awaiting_confirmation is True

    # Step 4: User confirms operation
    state = agent.process(state, confirmation="confirm")
    assert state.status == "executing"

    # Step 5: Agent executes tool actions against real SQLite DB session
    async with session_factory() as session:
        tools = BookingTools(session=session, user=user)
        state = await agent.execute(state, tools)

        assert state.status == "completed"
        assert state.result is not None
        appointment_id = state.result["id"]

        # Step 6: Direct DB verification
        db_appt = await session.get(Appointment, appointment_id)
        assert db_appt is not None
        assert db_appt.patient_id == patient.id
        assert db_appt.organization_id == user.organization_id
        assert db_appt.reason == "Routine Checkup"
        assert db_appt.status == "confirmed"
        assert db_appt.starts_at == datetime(2026, 10, 11, 10, 0, 0)
 
 
@pytest.mark.asyncio
async def test_e2e_followup_pipeline_user_message_to_db() -> None:
    """
    Test End-to-End Pipeline for FollowUp:
    User Message -> LLM Extractor -> FollowUpExtraction -> FollowUpState -> FollowUpAgent -> FollowUpTools -> Database
    """
    user, patient = await _make_user_and_patient()
    extractor = FollowUpExtractor(api_key="test-key")

    mock_response = AsyncMock()
    mock_response.choices = [
        AsyncMock(
            message=AsyncMock(
                content='{"action": "create", "confirmation": "unknown", "followup_type": "call", "date": "tomorrow", "time": "14:00", "appointment_id": null, "followup_id": null, "reason": "Post-op status check"}'
            )
        )
    ]

    fixed_now = datetime(2026, 10, 10, 8, 0, 0, tzinfo=timezone.utc)

    # Step 1: User message -> Extractor
    with patch.object(extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
        extraction = await extractor.extract("Schedule a call follow-up tomorrow at 14:00 for Post-op status check")

    # Step 2: Build state
    state = build_followup_state(
        extraction,
        patient_id=str(patient.id),
        timezone="UTC",
        now=fixed_now,
    )
    assert state.action == "create"
    assert state.followup_type == "call"
    assert state.due_at == datetime(2026, 10, 11, 14, 0, 0, tzinfo=timezone.utc)

    # Step 3: Agent process
    agent = FollowUpAgent()
    state = agent.process(state)
    assert state.status == "confirming"

    # Step 4: User confirms
    state = agent.process(state, confirmation="confirm")
    assert state.status == "executing"

    # Step 5: Agent execution with FollowUpTools
    async with session_factory() as session:
        tools = FollowUpTools(session=session, user=user)
        state = await agent.execute(state, tools)

        assert state.status == "completed"
        followup_id = state.result["id"]

        # Step 6: Verify in Database
        db_followup = await session.get(FollowUp, followup_id)
        assert db_followup is not None
        assert db_followup.patient_id == patient.id
        assert db_followup.organization_id == user.organization_id
        assert db_followup.followup_type == "call"
        assert db_followup.reason == "Post-op status check"
        assert db_followup.status == "pending"
        assert db_followup.due_at == datetime(2026, 10, 11, 14, 0, 0)


# ============================================================================
# 3. Edge Cases & Mock / Failure Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_llm_malformed_json_response_graceful_handling() -> None:
    """Verify that malformed JSON response from LLM is caught gracefully and defaults to action=unknown."""
    from fastapi import HTTPException
    extractor = BookingExtractor(api_key="test-key")

    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock(message=AsyncMock(content="Invalid Non-JSON response text!"))]

    with patch.object(extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(HTTPException) as exc_info:
            await extractor.extract("I want to book an appointment")
        assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_llm_openai_api_error_graceful_handling() -> None:
    """Verify that OpenAI API errors (auth, network, rate limit) are caught gracefully."""
    from fastapi import HTTPException
    extractor = BookingExtractor(api_key="test-key")

    with patch.object(extractor.client.chat.completions, "create", side_effect=OpenAIError("API rate limit exceeded")):
        with pytest.raises(HTTPException) as exc_info:
            await extractor.extract("Book cardiology appointment")
        assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_llm_unconfigured_client_graceful_handling() -> None:
    """Verify unconfigured LLM client handles extraction gracefully without throwing exceptions."""
    from fastapi import HTTPException
    extractor = BookingExtractor(api_key="unconfigured")
    with pytest.raises(HTTPException) as exc_info:
        await extractor.extract("Book cardiology appointment")
    assert exc_info.value.status_code == 503
