import inspect
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.ai.booking.agent import BookingAgent
from app.ai.booking.contracts import BookingExtraction
from app.ai.booking.state import BookingState, build_booking_state
from app.ai.booking.tools import BookingTools
from app.db import init_db, session_factory
from app.models import Appointment, Organization, Patient, ReminderJob, User
from app.services.appointments import (
    create_appointment,
    get_available_slots,
    reschedule_appointment,
    update_appointment_status,
)


_schema_initialized = False


async def _ensure_test_schema() -> None:
    global _schema_initialized
    if not _schema_initialized:
        await init_db()
        _schema_initialized = True


async def _make_user_and_patient() -> tuple[User, UUID]:
    await _ensure_test_schema()
    async with session_factory() as session:
        organization = Organization(name=f"Booking Direct Org {uuid4().hex[:6]}")
        session.add(organization)
        await session.flush()
        user = User(
            organization_id=organization.id,
            email=f"booking-direct-{uuid4().hex[:8]}@example.org",
            full_name="Booking Direct User",
            role="admin",
            password_hash="test-password-hash",
            onboarding_complete=True,
        )
        patient = Patient(
            organization_id=organization.id,
            medical_record_number=f"BOOK-DIRECT-{uuid4().hex[:8]}",
            given_name="Booking",
            family_name="Patient",
            date_of_birth=date(1990, 1, 1),
        )
        session.add_all([user, patient])
        await session.commit()
        return user, patient.id


class RecordingBookingTools:
    def __init__(self, slots: list[str] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.slots = slots or []
        self.book_appointment = AsyncMock(side_effect=self._book)
        self.get_available_slots = AsyncMock(side_effect=self._availability)
        self.modify_appointment = AsyncMock(side_effect=self._modify)
        self.cancel_appointment = AsyncMock(side_effect=self._cancel)

    async def _book(self, **kwargs):
        self.calls.append(("book_appointment", kwargs))
        return {"id": uuid4(), "status": "confirmed", **kwargs}

    async def _availability(self, target_date: str):
        self.calls.append(("get_available_slots", {"target_date": target_date}))
        return self.slots

    async def _modify(self, **kwargs):
        self.calls.append(("modify_appointment", kwargs))
        return {"id": kwargs["appointment_id"], "status": "confirmed", **kwargs}

    async def _cancel(self, **kwargs):
        self.calls.append(("cancel_appointment", kwargs))
        return {"id": kwargs["appointment_id"], "status": "cancelled"}


@pytest.mark.parametrize(
    ("action", "expected_tool", "extra"),
    [
        ("book", "book_appointment", {"specialty": "dermatology", "reason": "Dermatology visit"}),
        ("modify", "modify_appointment", {}),
        ("cancel", "cancel_appointment", {}),
    ],
)
@pytest.mark.asyncio
async def test_booking_agent_unit_actions_call_tools(
    action: str,
    expected_tool: str,
    extra: dict[str, object],
) -> None:
    patient_id = uuid4()
    appointment_id = uuid4()
    starts_at = datetime.now(timezone.utc) + timedelta(days=7)
    state = BookingState(
        patient_id=str(patient_id),
        appointment_id=str(appointment_id),
        action=action,
        starts_at=starts_at,
        status="collecting",
        **extra,
    )

    agent = BookingAgent()
    state = agent.process(state)
    transitions = [state.status]
    if state.awaiting_confirmation:
        state = agent.process(state, confirmation="confirm")
        transitions.append(state.status)

    tools = RecordingBookingTools()
    state = await agent.execute(state, tools)
    transitions.append(state.status)

    assert state.status == "completed"
    assert tools.calls[0][0] == expected_tool
    assert transitions[-1] == "completed"


def test_booking_agent_unit_missing_fields_confirmation_rejection_and_unknown() -> None:
    agent = BookingAgent()

    missing_specialty = agent.process(
        BookingState(
            action="book",
            patient_id=str(uuid4()),
            target_date="2026-10-20",
            selected_slot="2026-10-20T09:00:00+00:00",
            available_slots=["2026-10-20T09:00:00+00:00"],
            reason="Skin rash",
        )
    )
    assert missing_specialty.status == "collecting"
    assert missing_specialty.missing_fields == ["specialty"]

    missing_date = agent.process(
        BookingState(
            action="book",
            patient_id=str(uuid4()),
            specialty="dermatology",
            reason="Skin rash",
        )
    )
    assert missing_date.status == "collecting"
    assert missing_date.missing_fields == ["date_time"]

    ready = agent.process(
        BookingState(
            action="book",
            patient_id=str(uuid4()),
            specialty="dermatology",
            starts_at=datetime.now(timezone.utc) + timedelta(days=3),
            reason="Skin rash",
        )
    )
    assert ready.status == "confirming"
    assert ready.awaiting_confirmation is True

    rejected = agent.process(ready, confirmation="reject")
    assert rejected.status == "new"
    assert rejected.awaiting_confirmation is False
    assert rejected.result == {"message": "Operation rejected"}

    unknown = agent.process(BookingState(action="unknown", patient_id=str(uuid4())))
    assert unknown.status == "collecting"
    assert unknown.missing_fields == ["action"]
    assert unknown.awaiting_confirmation is False


@pytest.mark.asyncio
async def test_booking_agent_unit_availability_collection_and_invalid_input() -> None:
    target_date = (datetime.now(timezone.utc) + timedelta(days=8)).date().isoformat()
    state = BookingState(
        action="book",
        patient_id=str(uuid4()),
        specialty="dermatology",
        target_date=target_date,
        reason="Skin rash",
    )

    agent = BookingAgent()
    state = agent.process(state)
    assert state.status == "executing"

    tools = RecordingBookingTools(slots=[f"{target_date}T09:00:00+00:00"])
    state = await agent.execute(state, tools)
    assert state.status == "collecting"
    assert state.available_slots == [f"{target_date}T09:00:00+00:00"]
    assert state.missing_fields == ["selected_slot"]
    assert tools.calls == [("get_available_slots", {"target_date": target_date})]

    # To reach the datetime.fromisoformat check the bad slot must be IN available_slots
    # (otherwise the agent short-circuits with "Selected slot is not available." first).
    state.available_slots = ["not-a-date"]
    state.selected_slot = "not-a-date"
    state.status = "executing"
    failed = await agent.execute(state, tools)
    assert failed.status == "failed"
    assert failed.error == "Invalid slot format."


@pytest.mark.asyncio
async def test_booking_agent_unit_failed_execution_without_tool_call() -> None:
    tools = RecordingBookingTools()
    state = BookingState(
        action="cancel",
        patient_id=str(uuid4()),
        appointment_id="not-a-uuid",
        status="executing",
    )

    result = await BookingAgent().execute(state, tools)

    assert result.status == "failed"
    assert "badly formed hexadecimal UUID" in result.error
    assert tools.calls == []


def test_booking_agent_unit_does_not_access_database_or_http() -> None:
    source = inspect.getsource(BookingAgent)

    assert "session" not in source
    assert "select(" not in source
    assert "app.db" not in source
    assert "app.models" not in source
    assert "httpx" not in source
    assert "requests" not in source


def test_booking_tools_unit_do_not_duplicate_service_database_logic() -> None:
    source = inspect.getsource(BookingTools)

    assert "session.add" not in source
    assert "session.commit" not in source
    assert "select(" not in source
    assert "from app.models" not in source


@pytest.mark.asyncio
async def test_booking_tools_unit_delegate_to_services_and_preserve_context() -> None:
    session = object()
    user = SimpleNamespace(organization_id=uuid4())
    patient_id = uuid4()
    appointment_id = uuid4()
    starts_at = datetime.now(timezone.utc) + timedelta(days=6)

    with (
        patch("app.ai.booking.tools.ensure_patient_access", new_callable=AsyncMock) as access,
        patch(
            "app.ai.booking.tools.create_appointment",
            new_callable=AsyncMock,
            return_value={"id": appointment_id, "status": "confirmed"},
        ) as create_service,
        patch(
            "app.ai.booking.tools.reschedule_appointment",
            new_callable=AsyncMock,
            return_value={"id": appointment_id, "status": "confirmed"},
        ) as reschedule_service,
        patch(
            "app.ai.booking.tools.update_appointment_status",
            new_callable=AsyncMock,
            return_value={"id": appointment_id, "status": "cancelled"},
        ) as status_service,
        patch(
            "app.services.appointments.get_available_slots",
            new_callable=AsyncMock,
            return_value=[starts_at],
        ) as availability_service,
    ):
        tools = BookingTools(session=session, user=user)

        await tools.book_appointment(patient_id, starts_at, "Skin rash")
        create_service.assert_awaited_once_with(
            session=session,
            organization_id=user.organization_id,
            patient_id=patient_id,
            starts_at=starts_at,
            reason="Skin rash",
            status="confirmed",
            user=user,
        )
        access.assert_awaited_once_with(session, patient_id, user, "appointments")

        slots = await tools.get_available_slots(starts_at.date().isoformat())
        assert slots == [starts_at.isoformat()]
        availability_service.assert_awaited_once()

        await tools.modify_appointment(appointment_id, starts_at=starts_at, reason="Updated")
        reschedule_service.assert_awaited_once_with(
            session=session,
            appointment_id=appointment_id,
            organization_id=user.organization_id,
            starts_at=starts_at,
            reason="Updated",
            user=user,
        )

        await tools.cancel_appointment(appointment_id)
        status_service.assert_awaited_once_with(
            session=session,
            appointment_id=appointment_id,
            status="cancelled",
            organization_id=user.organization_id,
            user=user,
        )


@pytest.mark.asyncio
async def test_booking_service_create_read_modify_cancel_and_persist() -> None:
    user, patient_id = await _make_user_and_patient()
    async with session_factory() as session:
        starts_at = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)
        created = await create_appointment(
            session=session,
            organization_id=user.organization_id,
            patient_id=patient_id,
            starts_at=starts_at,
            reason="Initial booking",
            status="confirmed",
            user=user,
        )
        appointment_id = created["id"]
        db_item = await session.get(Appointment, appointment_id)
        assert db_item is not None
        assert db_item.patient_id == patient_id
        assert db_item.status == "confirmed"
        reminder = await session.scalar(
            select(ReminderJob).where(ReminderJob.appointment_id == appointment_id)
        )
        assert reminder is not None
        assert reminder.status == "queued"

        slots = await get_available_slots(
            session=session,
            organization_id=user.organization_id,
            target_date=starts_at.date(),
        )
        assert starts_at.isoformat() not in [slot.isoformat() for slot in slots]

        updated_starts_at = (starts_at + timedelta(days=1)).replace(hour=10, minute=0)
        await reschedule_appointment(
            session=session,
            appointment_id=appointment_id,
            organization_id=user.organization_id,
            starts_at=updated_starts_at,
            reason="Updated booking",
            user=user,
        )
        db_item = await session.get(Appointment, appointment_id)
        assert db_item.starts_at == updated_starts_at
        assert db_item.reason == "Updated booking"

        await update_appointment_status(
            session=session,
            appointment_id=appointment_id,
            organization_id=user.organization_id,
            status="cancelled",
            user=user,
        )
        db_item = await session.get(Appointment, appointment_id)
        assert db_item.status == "cancelled"


@pytest.mark.asyncio
async def test_booking_service_boundaries_conflicts_and_invalid_statuses() -> None:
    user, patient_id = await _make_user_and_patient()
    other_user, _ = await _make_user_and_patient()
    async with session_factory() as session:
        starts_at = (datetime.now(timezone.utc) + timedelta(days=9)).replace(
            hour=11,
            minute=0,
            second=0,
            microsecond=0,
        )
        created = await create_appointment(
            session=session,
            organization_id=user.organization_id,
            patient_id=patient_id,
            starts_at=starts_at,
            reason="Conflict source",
            status="confirmed",
            user=user,
        )

        with pytest.raises(HTTPException) as duplicate:
            await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=starts_at,
                reason="Duplicate",
                status="confirmed",
                user=user,
            )
        assert duplicate.value.status_code == 409

        with pytest.raises(HTTPException) as past:
            await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=datetime.now(timezone.utc) - timedelta(days=1),
                reason="Past",
                status="confirmed",
                user=user,
            )
        assert past.value.status_code == 422

        with pytest.raises(HTTPException) as invalid_new_status:
            await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=starts_at + timedelta(days=1),
                reason="Invalid",
                status="arrived",
                user=user,
            )
        assert invalid_new_status.value.status_code == 422

        with pytest.raises(HTTPException) as cross_patient:
            await create_appointment(
                session=session,
                organization_id=other_user.organization_id,
                patient_id=patient_id,
                starts_at=starts_at + timedelta(days=2),
                reason="Cross-org patient",
                status="confirmed",
                user=other_user,
            )
        assert cross_patient.value.status_code == 404

        with pytest.raises(HTTPException) as cross_appointment:
            await reschedule_appointment(
                session=session,
                appointment_id=created["id"],
                organization_id=other_user.organization_id,
                starts_at=starts_at + timedelta(days=3),
                reason="Cross-org appointment",
                user=other_user,
            )
        assert cross_appointment.value.status_code == 404

        with pytest.raises(HTTPException) as invalid_status:
            await update_appointment_status(
                session=session,
                appointment_id=created["id"],
                organization_id=user.organization_id,
                status="done",
                user=user,
            )
        assert invalid_status.value.status_code == 422


@pytest.mark.asyncio
async def test_booking_agent_to_tool_to_service_to_database_real_chain() -> None:
    user, patient_id = await _make_user_and_patient()
    starts_at = (datetime.now(timezone.utc) + timedelta(days=10)).replace(
        hour=9,
        minute=0,
        second=0,
        microsecond=0,
    )
    state = BookingState(
        patient_id=str(patient_id),
        action="book",
        specialty="dermatology",
        starts_at=starts_at,
        reason="Dermatology visit",
    )

    agent = BookingAgent()
    state = agent.process(state)
    transitions = [state.status]
    assert state.status == "confirming"

    state = agent.process(state, confirmation="confirm")
    transitions.append(state.status)
    assert state.status == "executing"

    async with session_factory() as session:
        tools = BookingTools(session=session, user=user)
        state = await agent.execute(state, tools)
        transitions.append(state.status)

        assert transitions == ["confirming", "executing", "completed"]
        assert state.result is not None
        db_item = await session.get(Appointment, state.result["id"])
        assert db_item is not None
        assert db_item.patient_id == patient_id
        # SQLite strips tzinfo on round-trip; normalise before comparing.
        db_starts = db_item.starts_at if db_item.starts_at.tzinfo else db_item.starts_at.replace(tzinfo=timezone.utc)
        assert db_starts == starts_at
        assert db_item.status == "confirmed"
        assert db_item.reason == "Dermatology visit"


@pytest.mark.asyncio
async def test_booking_e2e_arabic_request_collects_availability_confirms_and_persists() -> None:
    user, patient_id = await _make_user_and_patient()
    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    initial = BookingExtraction(
        action="book",
        confirmation="unknown",
        specialty="dermatology",
        reason="كشف جلدية",
    )
    parsed = initial
    state = build_booking_state(
        parsed,
        patient_id=str(patient_id),
        conversation_id="booking-conversation-1",
        timezone="Africa/Cairo",
        now=now,
    )

    agent = BookingAgent()
    transitions = [state.status]
    state = agent.process(state)
    transitions.append(state.status)
    assert state.missing_fields == ["date_time"]

    followup = BookingExtraction(
        action="book",
        confirmation="unknown",
        specialty="dermatology",
        date="بعد أسبوع",
        reason="كشف جلدية",
    )
    updated = build_booking_state(
        followup,
        patient_id=str(patient_id),
        conversation_id=state.conversation_id,
        timezone="Africa/Cairo",
        now=now,
    )
    state.target_date = updated.target_date
    state.action = updated.action
    state.specialty = updated.specialty
    state.reason = updated.reason
    state = agent.process(state)
    transitions.append(state.status)
    assert state.status == "executing"

    async with session_factory() as session:
        tools = BookingTools(session=session, user=user)
        state = await agent.execute(state, tools)
        transitions.append(state.status)
        assert state.status == "collecting"
        assert state.available_slots

        selected_slot = state.available_slots[0]
        state.selected_slot = selected_slot
        state = agent.process(state)
        transitions.append(state.status)
        assert state.status == "confirming"

        state = agent.process(state, confirmation="confirm")
        transitions.append(state.status)
        assert state.status == "executing"

        state = await agent.execute(state, tools)
        transitions.append(state.status)

        assert transitions == [
            "collecting",
            "collecting",
            "executing",
            "collecting",
            "confirming",
            "executing",
            "completed",
        ]
        assert state.result is not None
        db_item = await session.get(Appointment, state.result["id"])
        assert db_item is not None
        assert db_item.patient_id == patient_id
        # SQLite strips tzinfo on round-trip; normalise before comparing.
        db_starts = db_item.starts_at if db_item.starts_at.tzinfo else db_item.starts_at.replace(tzinfo=timezone.utc)
        assert db_starts == datetime.fromisoformat(selected_slot)
        assert db_item.status == "confirmed"
        assert db_item.reason == "كشف جلدية"


@pytest.mark.asyncio
async def test_booking_real_lifecycle_create_read_modify_and_create_cancel() -> None:
    user, patient_id = await _make_user_and_patient()
    async with session_factory() as session:
        tools = BookingTools(session=session, user=user)
        starts_at = (datetime.now(timezone.utc) + timedelta(days=12)).replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0,
        )

        created = await tools.book_appointment(patient_id, starts_at, "Lifecycle")
        db_item = await session.get(Appointment, created["id"])
        assert db_item is not None
        # SQLite strips tzinfo on round-trip; normalise before comparing.
        db_starts = db_item.starts_at if db_item.starts_at.tzinfo else db_item.starts_at.replace(tzinfo=timezone.utc)
        assert db_starts == starts_at

        fetched_slots = await tools.get_available_slots(starts_at.date().isoformat())
        assert starts_at.isoformat() not in fetched_slots

        updated_start = starts_at + timedelta(days=1)
        updated = await tools.modify_appointment(
            created["id"],
            starts_at=updated_start,
            reason="Lifecycle updated",
        )
        assert updated["starts_at"] == updated_start
        db_item = await session.get(Appointment, created["id"])
        assert db_item.starts_at == updated_start
        assert db_item.reason == "Lifecycle updated"

        cancel_created = await tools.book_appointment(
            patient_id,
            starts_at + timedelta(days=2),
            "Cancel lifecycle",
        )
        cancelled = await tools.cancel_appointment(cancel_created["id"])
        assert cancelled["status"] == "cancelled"
        db_cancelled = await session.get(Appointment, cancel_created["id"])
        assert db_cancelled.status == "cancelled"
