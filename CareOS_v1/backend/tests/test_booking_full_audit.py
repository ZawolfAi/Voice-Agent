"""
Booking Agent — Complete Real-Workflow Test Audit
=================================================

Covers every layer demanded by the audit spec:
  Section 2  — BookingAgent Unit tests
  Section 3  — BookingTools Unit tests
  Section 4  — AppointmentService tests (REAL DB)
  Section 5  — Agent → Tool → Service → DB Integration (REAL, nothing mocked)
  Section 6  — E2E arabic-request workflow (REAL DB)
  Section 7  — Full appointment lifecycle CREATE→READ→MODIFY→CANCEL (REAL DB)
  Section 8  — Availability integration (REAL DB)
  Section 9  — Mock audit markers per class docstring

Database strategy
-----------------
conftest.py sets APP_ENV=test and DATABASE_URL to a process-scoped SQLite
file in /tmp. Tests that hit the DB call _ensure_test_schema() once per
process to drop/recreate all tables.  No production DB is touched.

Helper _dt() normalises a stored SQLite datetime (naive) to UTC-aware so
that assertions can compare directly with timezone-aware Python datetimes.
"""

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
from app.ai.booking.state import BookingState, build_booking_state, update_missing_fields
from app.ai.booking.tools import BookingTools
from app.db import init_db, session_factory
from app.models import Appointment, Organization, Patient, ReminderJob, User
from app.services.appointments import (
    create_appointment,
    get_available_slots,
    reschedule_appointment,
    update_appointment_status,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_schema_initialized = False


async def _ensure_test_schema() -> None:
    global _schema_initialized
    if not _schema_initialized:
        await init_db()
        _schema_initialized = True


def _dt(value: datetime) -> datetime:
    """Normalise a possibly-naive datetime (SQLite strips tzinfo) to UTC-aware."""
    if value is None:
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _future(days: int, hour: int = 10, minute: int = 0) -> datetime:
    """Return a deterministic future UTC datetime with no microseconds."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


async def _make_org_user_patient() -> tuple[User, UUID]:
    """
    Create a fresh Organisation + User + Patient in the test DB.
    Returns (user, patient_id). Each call creates an isolated org so
    org-boundary tests remain independent.
    """
    await _ensure_test_schema()
    suffix = uuid4().hex[:8]
    async with session_factory() as session:
        org = Organization(name=f"AuditOrg-{suffix}")
        session.add(org)
        await session.flush()

        user = User(
            organization_id=org.id,
            email=f"audit-{suffix}@test.org",
            full_name="Audit User",
            role="admin",
            password_hash="x",
            onboarding_complete=True,
        )
        patient = Patient(
            organization_id=org.id,
            medical_record_number=f"AUDIT-{suffix}",
            given_name="Audit",
            family_name="Patient",
            date_of_birth=date(1990, 6, 15),
        )
        session.add_all([user, patient])
        await session.commit()
        return user, patient.id


# ---------------------------------------------------------------------------
# Mock Tools — used ONLY in Unit tests (Section 2)
# ---------------------------------------------------------------------------

class _FakeTools:
    """
    Section 2: UNIT layer only.
    Records calls, never touches DB/service/HTTP.
    """

    def __init__(self, slots: list[str] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._slots = slots or []
        self.book_appointment = AsyncMock(side_effect=self._book)
        self.get_available_slots = AsyncMock(side_effect=self._get_slots)
        self.modify_appointment = AsyncMock(side_effect=self._modify)
        self.cancel_appointment = AsyncMock(side_effect=self._cancel)

    async def _book(self, **kw):
        self.calls.append(("book_appointment", kw))
        return {"id": uuid4(), "status": "confirmed", **kw}

    async def _get_slots(self, target_date: str):
        self.calls.append(("get_available_slots", {"target_date": target_date}))
        return self._slots

    async def _modify(self, **kw):
        self.calls.append(("modify_appointment", kw))
        return {"id": kw["appointment_id"], "status": "confirmed", **kw}

    async def _cancel(self, **kw):
        self.calls.append(("cancel_appointment", kw))
        return {"id": kw["appointment_id"], "status": "cancelled"}


# ===========================================================================
# SECTION 2 — BookingAgent UNIT tests
# Agent is exercised directly; _FakeTools mocks all tool calls.
# DB / Service / HTTP are NEVER reached here.
# ===========================================================================

class TestBookingAgentUnit:
    """
    CLASSIFICATION: UNIT
    Mocked: BookingTools (FakeTools)
    Not mocked: BookingAgent itself
    DB / Service: never touched
    """

    # --- 2a: intent routing --------------------------------------------------

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action", "expected_tool", "extra_state"),
        [
            (
                "book",
                "book_appointment",
                {"specialty": "dermatology", "reason": "Skin rash"},
            ),
            ("modify", "modify_appointment", {}),
            ("cancel", "cancel_appointment", {}),
        ],
    )
    async def test_correct_tool_called_for_each_action(
        self, action: str, expected_tool: str, extra_state: dict
    ) -> None:
        pid = str(uuid4())
        aid = str(uuid4())
        state = BookingState(
            patient_id=pid,
            appointment_id=aid,
            action=action,
            starts_at=_future(7),
            status="collecting",
            **extra_state,
        )
        agent = BookingAgent()
        state = agent.process(state)
        if state.awaiting_confirmation:
            state = agent.process(state, confirmation="confirm")

        tools = _FakeTools()
        state = await agent.execute(state, tools)

        assert state.status == "completed", f"Expected completed, got {state.status}: {state.error}"
        assert tools.calls[0][0] == expected_tool

    # --- 2b: unknown intent ---------------------------------------------------

    def test_unknown_intent_collected(self) -> None:
        agent = BookingAgent()
        state = agent.process(BookingState(action="unknown", patient_id=str(uuid4())))
        assert state.status == "collecting"
        assert "action" in state.missing_fields
        assert state.awaiting_confirmation is False

    # --- 2c: missing specialty ------------------------------------------------

    def test_missing_specialty_collected(self) -> None:
        agent = BookingAgent()
        state = agent.process(
            BookingState(
                action="book",
                patient_id=str(uuid4()),
                target_date="2026-11-01",
                selected_slot="2026-11-01T09:00:00+00:00",
                available_slots=["2026-11-01T09:00:00+00:00"],
                reason="headache",
            )
        )
        assert state.status == "collecting"
        assert "specialty" in state.missing_fields

    # --- 2d: missing date/time ------------------------------------------------

    def test_missing_date_time_collected(self) -> None:
        agent = BookingAgent()
        state = agent.process(
            BookingState(
                action="book",
                patient_id=str(uuid4()),
                specialty="cardiology",
                reason="palpitations",
            )
        )
        assert state.status == "collecting"
        assert "date_time" in state.missing_fields

    # --- 2e: missing reason ---------------------------------------------------

    def test_missing_reason_collected(self) -> None:
        agent = BookingAgent()
        state = agent.process(
            BookingState(
                action="book",
                patient_id=str(uuid4()),
                specialty="cardiology",
                starts_at=_future(5),
                # reason deliberately absent
            )
        )
        assert state.status == "collecting"
        assert "reason" in state.missing_fields

    # --- 2f: missing appointment_id for modify/cancel -------------------------

    @pytest.mark.parametrize("action", ["modify", "cancel"])
    def test_missing_appointment_id_collected(self, action: str) -> None:
        agent = BookingAgent()
        state = agent.process(
            BookingState(
                action=action,
                patient_id=str(uuid4()),
                starts_at=_future(5) if action == "modify" else None,
            )
        )
        assert state.status == "collecting"
        assert "appointment_id" in state.missing_fields

    # --- 2g: confirmation required when all fields present --------------------

    def test_confirmation_required_when_ready(self) -> None:
        agent = BookingAgent()
        state = agent.process(
            BookingState(
                action="book",
                patient_id=str(uuid4()),
                specialty="neurology",
                starts_at=_future(4),
                reason="headache",
            )
        )
        assert state.status == "confirming"
        assert state.awaiting_confirmation is True

    # --- 2h: confirmation accepted -------------------------------------------

    def test_confirmation_accepted(self) -> None:
        agent = BookingAgent()
        state = BookingState(
            action="book",
            patient_id=str(uuid4()),
            specialty="neurology",
            starts_at=_future(4),
            reason="headache",
        )
        state = agent.process(state)
        assert state.awaiting_confirmation is True
        state = agent.process(state, confirmation="confirm")
        assert state.status == "executing"
        assert state.awaiting_confirmation is False

    # --- 2i: confirmation rejected --------------------------------------------

    def test_confirmation_rejected(self) -> None:
        agent = BookingAgent()
        state = BookingState(
            action="book",
            patient_id=str(uuid4()),
            specialty="neurology",
            starts_at=_future(4),
            reason="headache",
        )
        state = agent.process(state)
        state = agent.process(state, confirmation="reject")
        assert state.status == "new"
        assert state.awaiting_confirmation is False
        assert state.result == {"message": "Operation rejected"}

    # --- 2j: new action while awaiting confirmation --------------------------

    def test_new_action_while_awaiting(self) -> None:
        agent = BookingAgent()
        state = BookingState(
            action="book",
            patient_id=str(uuid4()),
            specialty="neurology",
            starts_at=_future(4),
            reason="headache",
            awaiting_confirmation=True,
            status="confirming",
        )
        state = agent.process(state, new_action="cancel")
        assert state.action == "cancel"
        assert state.status == "collecting"
        assert state.awaiting_confirmation is False

    # --- 2k: invalid input (bad UUID) causes failed execution ----------------

    @pytest.mark.asyncio
    async def test_invalid_uuid_causes_failed_execution(self) -> None:
        tools = _FakeTools()
        state = BookingState(
            action="cancel",
            patient_id=str(uuid4()),
            appointment_id="not-a-uuid",
            status="executing",
        )
        result = await BookingAgent().execute(state, tools)
        assert result.status == "failed"
        assert "badly formed hexadecimal UUID" in result.error
        assert tools.calls == []  # no tool call attempted

    # --- 2l: availability collection flow and invalid slot format ------------

    @pytest.mark.asyncio
    async def test_availability_collection_flow(self) -> None:
        target_date = _future(9).date().isoformat()
        slot = f"{target_date}T10:00:00+00:00"
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

        tools = _FakeTools(slots=[slot])
        state = await agent.execute(state, tools)
        assert state.status == "collecting"
        assert state.available_slots == [slot]
        assert "selected_slot" in state.missing_fields
        assert tools.calls == [("get_available_slots", {"target_date": target_date})]

    @pytest.mark.asyncio
    async def test_invalid_slot_format_detected(self) -> None:
        """
        The agent only reaches the datetime.fromisoformat check when the slot
        IS in available_slots (so it passes the availability check) but is not
        parseable as an ISO datetime. Reproduce by adding the bad value to
        available_slots.
        """
        target_date = _future(9).date().isoformat()
        bad_slot = "not-a-date"
        state = BookingState(
            action="book",
            patient_id=str(uuid4()),
            specialty="dermatology",
            target_date=target_date,
            reason="Skin rash",
            available_slots=[bad_slot],   # slot IS in available list
            selected_slot=bad_slot,
            status="executing",
        )
        tools = _FakeTools(slots=[bad_slot])
        result = await BookingAgent().execute(state, tools)
        assert result.status == "failed"
        assert result.error == "Invalid slot format."

    @pytest.mark.asyncio
    async def test_slot_not_in_availability_is_rejected(self) -> None:
        """
        A selected_slot that is NOT in available_slots is rejected before
        attempting the datetime parse.
        """
        target_date = _future(9).date().isoformat()
        available = [f"{target_date}T10:00:00+00:00"]
        state = BookingState(
            action="book",
            patient_id=str(uuid4()),
            specialty="dermatology",
            target_date=target_date,
            reason="Skin rash",
            available_slots=available,
            selected_slot="not-a-date",   # not in available_slots
            status="executing",
        )
        tools = _FakeTools(slots=available)
        result = await BookingAgent().execute(state, tools)
        assert result.status == "collecting"
        assert "unavailable_choice" in result.missing_fields

    # --- 2m: failed execution when not in executing status -------------------

    @pytest.mark.asyncio
    async def test_execute_fails_if_not_in_executing_status(self) -> None:
        tools = _FakeTools()
        state = BookingState(
            action="book",
            patient_id=str(uuid4()),
            specialty="dermatology",
            starts_at=_future(3),
            reason="check",
            status="collecting",  # not "executing"
        )
        result = await BookingAgent().execute(state, tools)
        assert result.status == "failed"
        assert "not ready" in result.error.lower()

    # --- 2n: error state short-circuits to failed immediately ----------------

    def test_error_state_short_circuits(self) -> None:
        agent = BookingAgent()
        state = BookingState(error="pre-existing error")
        result = agent.process(state)
        assert result.status == "failed"

    # --- 2o: state transitions are deterministic -----------------------------

    @pytest.mark.asyncio
    async def test_full_state_transition_sequence(self) -> None:
        agent = BookingAgent()
        tools = _FakeTools()

        # new → collecting (missing date_time) → add date → executing (needs slots) →
        # collecting again (choose slot) → confirming → executing → completed
        state = BookingState(
            action="book",
            patient_id=str(uuid4()),
            specialty="dermatology",
            reason="rash",
        )
        s1 = agent.process(state)
        assert s1.status == "collecting"
        assert "date_time" in s1.missing_fields

        target_date = _future(10).date().isoformat()
        s1.target_date = target_date
        s2 = agent.process(s1)
        assert s2.status == "executing"

        slot = f"{target_date}T09:00:00+00:00"
        tools2 = _FakeTools(slots=[slot])
        s3 = await agent.execute(s2, tools2)
        assert s3.status == "collecting"
        assert "selected_slot" in s3.missing_fields

        s3.selected_slot = slot
        s4 = agent.process(s3)
        assert s4.status == "confirming"

        s5 = agent.process(s4, confirmation="confirm")
        assert s5.status == "executing"

        s6 = await agent.execute(s5, tools2)
        assert s6.status == "completed"

    # --- 2p: agent source does NOT touch DB / HTTP ---------------------------

    def test_agent_source_does_not_access_db_or_http(self) -> None:
        src = inspect.getsource(BookingAgent)
        assert "session" not in src
        assert "select(" not in src
        assert "app.db" not in src
        assert "app.models" not in src
        assert "httpx" not in src
        assert "requests" not in src


# ===========================================================================
# SECTION 3 — BookingTools UNIT tests
# Service layer is mocked; DB is never hit.
# ===========================================================================

class TestBookingToolsUnit:
    """
    CLASSIFICATION: TOOL
    Mocked: create_appointment, reschedule_appointment,
            update_appointment_status, get_available_slots (service functions),
            ensure_patient_access
    Not mocked: BookingTools itself
    DB: never touched
    """

    def test_tools_source_does_not_contain_db_logic(self) -> None:
        src = inspect.getsource(BookingTools)
        assert "session.add" not in src
        assert "session.commit" not in src
        assert "select(" not in src
        assert "from app.models" not in src

    @pytest.mark.asyncio
    async def test_book_delegates_correctly_and_enforces_patient_access(self) -> None:
        session = object()
        user = SimpleNamespace(organization_id=uuid4())
        patient_id = uuid4()
        starts_at = _future(5)
        ret = {"id": uuid4(), "status": "confirmed"}

        with (
            patch("app.ai.booking.tools.ensure_patient_access", new_callable=AsyncMock) as access,
            patch(
                "app.ai.booking.tools.create_appointment",
                new_callable=AsyncMock,
                return_value=ret,
            ) as create_svc,
        ):
            tools = BookingTools(session=session, user=user)
            result = await tools.book_appointment(patient_id, starts_at, "test reason")

        assert result == ret
        access.assert_awaited_once_with(session, patient_id, user, "appointments")
        create_svc.assert_awaited_once_with(
            session=session,
            organization_id=user.organization_id,
            patient_id=patient_id,
            starts_at=starts_at,
            reason="test reason",
            status="confirmed",
            user=user,
        )

    @pytest.mark.asyncio
    async def test_modify_delegates_correctly(self) -> None:
        session = object()
        user = SimpleNamespace(organization_id=uuid4())
        appointment_id = uuid4()
        starts_at = _future(6)
        ret = {"id": appointment_id, "status": "confirmed"}

        with patch(
            "app.ai.booking.tools.reschedule_appointment",
            new_callable=AsyncMock,
            return_value=ret,
        ) as svc:
            tools = BookingTools(session=session, user=user)
            result = await tools.modify_appointment(
                appointment_id, starts_at=starts_at, reason="updated"
            )

        assert result == ret
        svc.assert_awaited_once_with(
            session=session,
            appointment_id=appointment_id,
            organization_id=user.organization_id,
            starts_at=starts_at,
            reason="updated",
            user=user,
        )

    @pytest.mark.asyncio
    async def test_cancel_delegates_correctly(self) -> None:
        session = object()
        user = SimpleNamespace(organization_id=uuid4())
        appointment_id = uuid4()
        ret = {"id": appointment_id, "status": "cancelled"}

        with patch(
            "app.ai.booking.tools.update_appointment_status",
            new_callable=AsyncMock,
            return_value=ret,
        ) as svc:
            tools = BookingTools(session=session, user=user)
            result = await tools.cancel_appointment(appointment_id)

        assert result == ret
        svc.assert_awaited_once_with(
            session=session,
            appointment_id=appointment_id,
            status="cancelled",
            organization_id=user.organization_id,
            user=user,
        )

    @pytest.mark.asyncio
    async def test_get_slots_delegates_correctly_and_returns_iso_strings(self) -> None:
        session = object()
        user = SimpleNamespace(organization_id=uuid4())
        slot_dt = _future(4)

        with patch(
            "app.services.appointments.get_available_slots",
            new_callable=AsyncMock,
            return_value=[slot_dt],
        ) as svc:
            tools = BookingTools(session=session, user=user)
            results = await tools.get_available_slots(slot_dt.date().isoformat())

        assert results == [slot_dt.isoformat()]
        svc.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_patient_context_is_preserved_across_calls(self) -> None:
        """
        Each tool method must pass self.session and self.user through to the
        service — they must not substitute a different session or user.
        """
        sentinel_session = object()
        sentinel_user = SimpleNamespace(organization_id=uuid4())
        patient_id = uuid4()
        appointment_id = uuid4()
        starts_at = _future(5)

        captured: list[dict] = []

        async def _capture_create(**kw):
            captured.append(kw)
            return {"id": appointment_id, "status": "confirmed"}

        async def _capture_reschedule(**kw):
            captured.append(kw)
            return {"id": appointment_id, "status": "confirmed"}

        async def _capture_cancel(**kw):
            captured.append(kw)
            return {"id": appointment_id, "status": "cancelled"}

        with (
            patch("app.ai.booking.tools.ensure_patient_access", new_callable=AsyncMock),
            patch("app.ai.booking.tools.create_appointment", side_effect=_capture_create),
            patch("app.ai.booking.tools.reschedule_appointment", side_effect=_capture_reschedule),
            patch("app.ai.booking.tools.update_appointment_status", side_effect=_capture_cancel),
        ):
            tools = BookingTools(session=sentinel_session, user=sentinel_user)
            await tools.book_appointment(patient_id, starts_at, "reason")
            await tools.modify_appointment(appointment_id, starts_at=starts_at)
            await tools.cancel_appointment(appointment_id)

        for call in captured:
            assert call["session"] is sentinel_session
            assert call["user"] is sentinel_user


# ===========================================================================
# SECTION 4 — AppointmentService tests (REAL test database, no mocks)
# ===========================================================================

class TestAppointmentServiceReal:
    """
    CLASSIFICATION: SERVICE
    Mocked: nothing
    DB: real SQLite test database (isolated, process-scoped)
    All assertions verified against DB rows.
    """

    # --- 4a: CREATE and verify DB row ----------------------------------------

    @pytest.mark.asyncio
    async def test_create_persists_appointment_and_reminder(self) -> None:
        user, patient_id = await _make_org_user_patient()
        starts_at = _future(7)

        async with session_factory() as session:
            result = await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=starts_at,
                reason="Initial booking",
                status="confirmed",
                user=user,
            )

        appointment_id = result["id"]

        # ---- DB verification ----
        async with session_factory() as session:
            db_item = await session.get(Appointment, appointment_id)
            assert db_item is not None, "Appointment not found in DB"
            assert db_item.patient_id == patient_id
            assert _dt(db_item.starts_at) == _dt(starts_at)
            assert db_item.status == "confirmed"
            assert db_item.reason == "Initial booking"

            reminder = await session.scalar(
                select(ReminderJob).where(ReminderJob.appointment_id == appointment_id)
            )
            assert reminder is not None, "ReminderJob not created"
            assert reminder.status == "queued"

    # --- 4b: READ availability (slot occupied check) -------------------------

    @pytest.mark.asyncio
    async def test_booked_slot_disappears_from_availability(self) -> None:
        user, patient_id = await _make_org_user_patient()
        starts_at = _future(8)

        async with session_factory() as session:
            await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=starts_at,
                reason="Occupying slot",
                status="confirmed",
                user=user,
            )
            slots = await get_available_slots(
                session=session,
                organization_id=user.organization_id,
                target_date=starts_at.date(),
            )

        slot_isos = [s.isoformat() for s in slots]
        assert starts_at.isoformat() not in slot_isos, (
            "Booked slot should not appear in availability"
        )

    # --- 4c: MODIFY and verify DB row ----------------------------------------

    @pytest.mark.asyncio
    async def test_reschedule_persists_new_datetime_and_reason(self) -> None:
        user, patient_id = await _make_org_user_patient()
        starts_at = _future(9)
        new_starts_at = _future(10)

        async with session_factory() as session:
            created = await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=starts_at,
                reason="Original",
                status="confirmed",
                user=user,
            )
            await reschedule_appointment(
                session=session,
                appointment_id=created["id"],
                organization_id=user.organization_id,
                starts_at=new_starts_at,
                reason="Rescheduled",
                user=user,
            )
            db_item = await session.get(Appointment, created["id"])

        assert _dt(db_item.starts_at) == _dt(new_starts_at)
        assert db_item.reason == "Rescheduled"

    # --- 4d: CANCEL and verify DB row ----------------------------------------

    @pytest.mark.asyncio
    async def test_cancel_persists_cancelled_status(self) -> None:
        user, patient_id = await _make_org_user_patient()

        async with session_factory() as session:
            created = await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=_future(11),
                reason="Cancel me",
                status="confirmed",
                user=user,
            )
            await update_appointment_status(
                session=session,
                appointment_id=created["id"],
                organization_id=user.organization_id,
                status="cancelled",
                user=user,
            )
            db_item = await session.get(Appointment, created["id"])

        assert db_item.status == "cancelled"

    # --- 4e: duplicate conflict -----------------------------------------------

    @pytest.mark.asyncio
    async def test_duplicate_slot_raises_409(self) -> None:
        user, patient_id = await _make_org_user_patient()
        starts_at = _future(12)

        async with session_factory() as session:
            await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=starts_at,
                reason="First",
                status="confirmed",
                user=user,
            )
            with pytest.raises(HTTPException) as exc_info:
                await create_appointment(
                    session=session,
                    organization_id=user.organization_id,
                    patient_id=patient_id,
                    starts_at=starts_at,
                    reason="Duplicate",
                    status="confirmed",
                    user=user,
                )
        assert exc_info.value.status_code == 409

    # --- 4f: past appointment rejected ----------------------------------------

    @pytest.mark.asyncio
    async def test_past_appointment_raises_422(self) -> None:
        user, patient_id = await _make_org_user_patient()

        async with session_factory() as session:
            with pytest.raises(HTTPException) as exc_info:
                await create_appointment(
                    session=session,
                    organization_id=user.organization_id,
                    patient_id=patient_id,
                    starts_at=datetime.now(timezone.utc) - timedelta(hours=1),
                    reason="Past",
                    status="confirmed",
                    user=user,
                )
        assert exc_info.value.status_code == 422

    # --- 4g: cross-org patient access rejected --------------------------------

    @pytest.mark.asyncio
    async def test_cross_org_patient_raises_404(self) -> None:
        user_a, patient_a = await _make_org_user_patient()
        user_b, _ = await _make_org_user_patient()

        async with session_factory() as session:
            with pytest.raises(HTTPException) as exc_info:
                await create_appointment(
                    session=session,
                    organization_id=user_b.organization_id,
                    patient_id=patient_a,  # patient belongs to org A
                    starts_at=_future(5),
                    reason="Cross-org",
                    status="confirmed",
                    user=user_b,
                )
        assert exc_info.value.status_code == 404

    # --- 4h: cross-org appointment access rejected ---------------------------

    @pytest.mark.asyncio
    async def test_cross_org_appointment_reschedule_raises_404(self) -> None:
        user_a, patient_a = await _make_org_user_patient()
        user_b, _ = await _make_org_user_patient()

        async with session_factory() as session:
            created = await create_appointment(
                session=session,
                organization_id=user_a.organization_id,
                patient_id=patient_a,
                starts_at=_future(5),
                reason="Org A appt",
                status="confirmed",
                user=user_a,
            )
            with pytest.raises(HTTPException) as exc_info:
                await reschedule_appointment(
                    session=session,
                    appointment_id=created["id"],
                    organization_id=user_b.organization_id,
                    starts_at=_future(6),
                    reason="Cross-org",
                    user=user_b,
                )
        assert exc_info.value.status_code == 404

    # --- 4i: invalid status rejected -----------------------------------------

    @pytest.mark.asyncio
    async def test_invalid_status_raises_422(self) -> None:
        user, patient_id = await _make_org_user_patient()

        async with session_factory() as session:
            created = await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=_future(5),
                reason="Status test",
                status="confirmed",
                user=user,
            )
            with pytest.raises(HTTPException) as exc_info:
                await update_appointment_status(
                    session=session,
                    appointment_id=created["id"],
                    organization_id=user.organization_id,
                    status="does-not-exist",
                    user=user,
                )
        assert exc_info.value.status_code == 422

    # --- 4j: cancelled appointment cannot be reopened -----------------------

    @pytest.mark.asyncio
    async def test_cancelled_appointment_cannot_be_reopened(self) -> None:
        user, patient_id = await _make_org_user_patient()

        async with session_factory() as session:
            created = await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=_future(5),
                reason="Reopen test",
                status="confirmed",
                user=user,
            )
            await update_appointment_status(
                session=session,
                appointment_id=created["id"],
                organization_id=user.organization_id,
                status="cancelled",
                user=user,
            )
            with pytest.raises(HTTPException) as exc_info:
                await update_appointment_status(
                    session=session,
                    appointment_id=created["id"],
                    organization_id=user.organization_id,
                    status="confirmed",
                    user=user,
                )
        assert exc_info.value.status_code == 409

    # --- 4k: invalid new-appointment status rejected -------------------------

    @pytest.mark.asyncio
    async def test_invalid_new_appointment_status_raises_422(self) -> None:
        user, patient_id = await _make_org_user_patient()

        async with session_factory() as session:
            with pytest.raises(HTTPException) as exc_info:
                await create_appointment(
                    session=session,
                    organization_id=user.organization_id,
                    patient_id=patient_id,
                    starts_at=_future(5),
                    reason="Bad status",
                    status="arrived",  # not in VALID_NEW_STATUSES
                    user=user,
                )
        assert exc_info.value.status_code == 422


# ===========================================================================
# SECTION 8 — Availability Integration (REAL DB, no mocks)
# ===========================================================================

class TestAvailabilityReal:
    """
    CLASSIFICATION: SERVICE / INTEGRATION
    Mocked: nothing
    DB: real SQLite test database
    Verifies get_available_slots returns data derived from actual DB state.
    """

    @pytest.mark.asyncio
    async def test_available_slot_returned_when_no_bookings(self) -> None:
        user, _ = await _make_org_user_patient()
        target = _future(14).date()

        async with session_factory() as session:
            slots = await get_available_slots(
                session=session,
                organization_id=user.organization_id,
                target_date=target,
            )
        assert len(slots) > 0, "Should have available slots for a fresh org"

    @pytest.mark.asyncio
    async def test_occupied_slot_excluded_from_availability(self) -> None:
        user, patient_id = await _make_org_user_patient()
        starts_at = _future(15, hour=9)

        async with session_factory() as session:
            await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=starts_at,
                reason="Occupy",
                status="confirmed",
                user=user,
            )
            slots = await get_available_slots(
                session=session,
                organization_id=user.organization_id,
                target_date=starts_at.date(),
            )

        slot_isos = [s.isoformat() for s in slots]
        assert starts_at.isoformat() not in slot_isos

    @pytest.mark.asyncio
    async def test_cancelled_appointment_frees_slot(self) -> None:
        user, patient_id = await _make_org_user_patient()
        starts_at = _future(16, hour=10)

        async with session_factory() as session:
            created = await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=starts_at,
                reason="Cancel slot test",
                status="confirmed",
                user=user,
            )
            # Slot should be occupied
            slots_before = await get_available_slots(
                session=session,
                organization_id=user.organization_id,
                target_date=starts_at.date(),
            )
            assert starts_at.isoformat() not in [s.isoformat() for s in slots_before]

            await update_appointment_status(
                session=session,
                appointment_id=created["id"],
                organization_id=user.organization_id,
                status="cancelled",
                user=user,
            )
            # Slot should be free now
            slots_after = await get_available_slots(
                session=session,
                organization_id=user.organization_id,
                target_date=starts_at.date(),
            )

        assert starts_at.isoformat() in [s.isoformat() for s in slots_after]

    @pytest.mark.asyncio
    async def test_multiple_slots_available_fresh_org(self) -> None:
        user, _ = await _make_org_user_patient()
        target = _future(17).date()

        async with session_factory() as session:
            slots = await get_available_slots(
                session=session,
                organization_id=user.organization_id,
                target_date=target,
            )
        # 09:00–17:00 at 30-min intervals = 16 slots for a future date
        assert len(slots) >= 10

    @pytest.mark.asyncio
    async def test_past_date_raises_400(self) -> None:
        user, _ = await _make_org_user_patient()
        past = datetime.now(timezone.utc).date() - timedelta(days=1)

        async with session_factory() as session:
            with pytest.raises(HTTPException) as exc_info:
                await get_available_slots(
                    session=session,
                    organization_id=user.organization_id,
                    target_date=past,
                )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_availability_is_org_scoped(self) -> None:
        """Booking in org A must not affect slots visible to org B."""
        user_a, patient_a = await _make_org_user_patient()
        user_b, _ = await _make_org_user_patient()
        starts_at = _future(18, hour=9)

        async with session_factory() as session:
            await create_appointment(
                session=session,
                organization_id=user_a.organization_id,
                patient_id=patient_a,
                starts_at=starts_at,
                reason="Org A booking",
                status="confirmed",
                user=user_a,
            )
            slots_b = await get_available_slots(
                session=session,
                organization_id=user_b.organization_id,
                target_date=starts_at.date(),
            )

        # The slot occupied in org A should still be free for org B
        assert starts_at.isoformat() in [s.isoformat() for s in slots_b]

    @pytest.mark.asyncio
    async def test_tools_get_slots_calls_real_service(self) -> None:
        """
        BookingTools.get_available_slots must pass through to the real service
        and return ISO strings derived from actual DB state.
        This is the Tool → Service → DB path for availability.
        """
        user, patient_id = await _make_org_user_patient()
        target_date_dt = _future(19, hour=9)

        async with session_factory() as session:
            # Book one slot so it's occupied
            await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=target_date_dt,
                reason="Block slot",
                status="confirmed",
                user=user,
            )
            tools = BookingTools(session=session, user=user)
            slots = await tools.get_available_slots(target_date_dt.date().isoformat())

        assert isinstance(slots, list)
        # Occupied slot must not appear in tool output
        assert target_date_dt.isoformat() not in slots
        # At least some other slots should be available
        assert len(slots) > 0


# ===========================================================================
# SECTION 5 — Agent → Tool → Service → Real DB Integration
# Nothing mocked except external LLM (extraction is pre-built).
# ===========================================================================

class TestAgentToolServiceIntegration:
    """
    CLASSIFICATION: INTEGRATION
    Mocked: nothing below BookingAgent
    DB: real SQLite test database
    Final assertion: DB row, not just state.status
    """

    @pytest.mark.asyncio
    async def test_full_chain_book_confirms_and_persists(self) -> None:
        """
        BookingAgent → BookingTools → AppointmentService → DB

        Steps:
        1. Build BookingState (extraction already structured — no LLM)
        2. agent.process() → confirming
        3. agent.process(confirmation=confirm) → executing
        4. agent.execute(real_tools) → completed
        5. Assert DB row exists with correct patient/datetime/status
        """
        user, patient_id = await _make_org_user_patient()
        starts_at = _future(20)

        state = BookingState(
            patient_id=str(patient_id),
            action="book",
            specialty="dermatology",
            starts_at=starts_at,
            reason="Audit integration test",
        )

        agent = BookingAgent()
        transitions: list[str] = []

        # Step 1: process → should go to confirming
        state = agent.process(state)
        transitions.append(state.status)
        assert state.status == "confirming", f"Expected confirming, got {state.status}"
        assert state.awaiting_confirmation is True

        # Step 2: user confirms
        state = agent.process(state, confirmation="confirm")
        transitions.append(state.status)
        assert state.status == "executing"

        # Step 3: execute with REAL tools against REAL DB
        async with session_factory() as session:
            tools = BookingTools(session=session, user=user)
            state = await agent.execute(state, tools)
            transitions.append(state.status)

            assert state.status == "completed", f"Failed: {state.error}"
            assert state.result is not None
            appointment_id = state.result["id"]

            # ---- FINAL DB ASSERTION ----
            db_item = await session.get(Appointment, appointment_id)
            assert db_item is not None, "Appointment not persisted in DB"
            assert db_item.patient_id == patient_id
            assert _dt(db_item.starts_at) == _dt(starts_at)
            assert db_item.status == "confirmed"
            assert db_item.reason == "Audit integration test"

        assert transitions == ["confirming", "executing", "completed"]

    @pytest.mark.asyncio
    async def test_full_chain_cancel_persists(self) -> None:
        user, patient_id = await _make_org_user_patient()

        # First book an appointment directly via service
        async with session_factory() as session:
            created = await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=_future(21),
                reason="To be cancelled by agent",
                status="confirmed",
                user=user,
            )
        appointment_id = created["id"]

        # Now use agent → tool → service to cancel it
        state = BookingState(
            patient_id=str(patient_id),
            appointment_id=str(appointment_id),
            action="cancel",
        )

        agent = BookingAgent()
        state = agent.process(state)
        assert state.status == "confirming"

        state = agent.process(state, confirmation="confirm")
        assert state.status == "executing"

        async with session_factory() as session:
            tools = BookingTools(session=session, user=user)
            state = await agent.execute(state, tools)

            assert state.status == "completed", f"Failed: {state.error}"

            # ---- DB ASSERTION ----
            db_item = await session.get(Appointment, appointment_id)
            assert db_item.status == "cancelled"

    @pytest.mark.asyncio
    async def test_full_chain_modify_persists(self) -> None:
        user, patient_id = await _make_org_user_patient()
        original_starts_at = _future(22)
        new_starts_at = _future(23)

        async with session_factory() as session:
            created = await create_appointment(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                starts_at=original_starts_at,
                reason="To be rescheduled by agent",
                status="confirmed",
                user=user,
            )
        appointment_id = created["id"]

        state = BookingState(
            patient_id=str(patient_id),
            appointment_id=str(appointment_id),
            action="modify",
            starts_at=new_starts_at,
            reason="Rescheduled by agent",
        )

        agent = BookingAgent()
        state = agent.process(state)
        assert state.status == "confirming"

        state = agent.process(state, confirmation="confirm")
        assert state.status == "executing"

        async with session_factory() as session:
            tools = BookingTools(session=session, user=user)
            state = await agent.execute(state, tools)

            assert state.status == "completed", f"Failed: {state.error}"

            # ---- DB ASSERTION ----
            db_item = await session.get(Appointment, appointment_id)
            assert _dt(db_item.starts_at) == _dt(new_starts_at)
            assert db_item.reason == "Rescheduled by agent"

    @pytest.mark.asyncio
    async def test_tools_enforces_cross_org_access(self) -> None:
        user_a, patient_a = await _make_org_user_patient()
        user_b, _ = await _make_org_user_patient()

        async with session_factory() as session:
            tools_b = BookingTools(session=session, user=user_b)
            with pytest.raises(HTTPException) as exc_info:
                await tools_b.book_appointment(
                    patient_id=patient_a,
                    starts_at=_future(5),
                    reason="Cross-org via tools",
                )
        assert exc_info.value.status_code == 404


# ===========================================================================
# SECTION 6 — E2E Workflow (Arabic request, REAL DB)
# Full realistic booking flow from user text → DB record
# ===========================================================================

class TestE2EBookingWorkflow:
    """
    CLASSIFICATION: E2E
    Mocked: LLM only (extraction represented as pre-built BookingExtraction)
    DB: real SQLite test database
    Final assertion: DB row
    """

    @pytest.mark.asyncio
    async def test_arabic_request_collects_date_gets_slots_confirms_and_persists(self) -> None:
        """
        Full flow:
          User: "عايز احجز جلدية"
          → Agent: missing date_time
          User provides: "بعد أسبوع"
          → Agent: executing (needs slots)
          → Tool → Service → DB (get_available_slots)
          → Agent: collecting (choose slot)
          User: selects first slot
          → Agent: confirming
          User: confirms
          → Agent: executing
          → Tool → Service → DB (create_appointment)
          Final: DB row verified
        """
        user, patient_id = await _make_org_user_patient()
        # Freeze "now" so "بعد أسبوع" is deterministic
        now = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)

        # Turn 1: user says "عايز احجز جلدية" — extraction has action+specialty+reason
        extraction_1 = BookingExtraction(
            action="book",
            specialty="dermatology",
            reason="كشف جلدية",
        )
        state = build_booking_state(
            extraction_1,
            patient_id=str(patient_id),
            conversation_id="e2e-arabic-001",
            timezone="Africa/Cairo",
            now=now,
        )

        agent = BookingAgent()
        transitions: list[str] = [state.status]

        # Agent should ask for date
        state = agent.process(state)
        transitions.append(state.status)
        assert "date_time" in state.missing_fields, f"Expected date_time missing, got {state.missing_fields}"

        # Turn 2: user provides "بعد أسبوع"
        extraction_2 = BookingExtraction(
            action="book",
            specialty="dermatology",
            date="بعد أسبوع",
            reason="كشف جلدية",
        )
        update = build_booking_state(
            extraction_2,
            patient_id=str(patient_id),
            conversation_id=state.conversation_id,
            timezone="Africa/Cairo",
            now=now,
        )
        state.target_date = update.target_date
        state.reason = update.reason

        state = agent.process(state)
        transitions.append(state.status)
        assert state.status == "executing", (
            f"Expected executing (needs slots), got {state.status}: {state.missing_fields}"
        )

        async with session_factory() as session:
            tools = BookingTools(session=session, user=user)

            # Execute: fetch availability from REAL DB
            state = await agent.execute(state, tools)
            transitions.append(state.status)
            assert state.status == "collecting", f"Expected collecting after slots, got {state.status}"
            assert state.available_slots, "Expected at least one available slot"

            # User selects first slot
            selected_slot = state.available_slots[0]
            state.selected_slot = selected_slot

            # Agent now has all info → confirming
            state = agent.process(state)
            transitions.append(state.status)
            assert state.status == "confirming"

            # User confirms
            state = agent.process(state, confirmation="confirm")
            transitions.append(state.status)
            assert state.status == "executing"

            # Execute: book appointment in REAL DB
            state = await agent.execute(state, tools)
            transitions.append(state.status)
            assert state.status == "completed", f"Failed: {state.error}"

            # ---- FINAL DB ASSERTION ----
            assert state.result is not None
            appointment_id = state.result["id"]
            db_item = await session.get(Appointment, appointment_id)

            assert db_item is not None, "Appointment not found in DB"
            assert db_item.patient_id == patient_id
            assert db_item.reason == "كشف جلدية"
            assert db_item.status == "confirmed"
            assert _dt(db_item.starts_at) == datetime.fromisoformat(selected_slot)

        # Validate transitions
        expected_prefix = ["collecting", "collecting", "executing", "collecting", "confirming", "executing", "completed"]
        assert transitions == expected_prefix, f"Unexpected transitions: {transitions}"

    @pytest.mark.asyncio
    async def test_e2e_with_exact_datetime_skips_availability_step(self) -> None:
        """
        When the user provides an exact datetime (date+time), the agent should
        skip the availability-collection step and go straight to confirming.
        """
        user, patient_id = await _make_org_user_patient()
        now = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)

        extraction = BookingExtraction(
            action="book",
            specialty="cardiology",
            date="2026-11-15",
            time="14:00",
            reason="قلب",
        )
        state = build_booking_state(
            extraction,
            patient_id=str(patient_id),
            timezone="Africa/Cairo",
            now=now,
        )

        agent = BookingAgent()
        state = agent.process(state)
        assert state.status == "confirming", f"Should confirm directly, got {state.status}"

        state = agent.process(state, confirmation="confirm")
        assert state.status == "executing"

        async with session_factory() as session:
            tools = BookingTools(session=session, user=user)
            state = await agent.execute(state, tools)

            assert state.status == "completed", f"Failed: {state.error}"
            db_item = await session.get(Appointment, state.result["id"])
            assert db_item is not None
            assert db_item.reason == "قلب"
            assert db_item.patient_id == patient_id


# ===========================================================================
# SECTION 7 — Full Appointment Lifecycle (REAL DB)
# CREATE → READ/VERIFY → MODIFY → VERIFY
# CREATE → CANCEL → VERIFY
# ===========================================================================

class TestBookingLifecycleReal:
    """
    CLASSIFICATION: INTEGRATION / LIFECYCLE
    Mocked: nothing
    DB: real SQLite test database
    Every mutation verified against DB.
    """

    @pytest.mark.asyncio
    async def test_create_read_modify_verify(self) -> None:
        user, patient_id = await _make_org_user_patient()
        starts_at = _future(25)
        new_starts = _future(26)

        async with session_factory() as session:
            tools = BookingTools(session=session, user=user)

            # CREATE
            created = await tools.book_appointment(patient_id, starts_at, "Lifecycle")
            appt_id = created["id"]

            # READ/VERIFY
            db_item = await session.get(Appointment, appt_id)
            assert db_item is not None
            assert _dt(db_item.starts_at) == _dt(starts_at)
            assert db_item.reason == "Lifecycle"
            assert db_item.status == "confirmed"

            # MODIFY
            updated = await tools.modify_appointment(
                appt_id,
                starts_at=new_starts,
                reason="Lifecycle updated",
            )

            # VERIFY MODIFY
            db_item = await session.get(Appointment, appt_id)
            assert _dt(db_item.starts_at) == _dt(new_starts)
            assert db_item.reason == "Lifecycle updated"
            assert updated["starts_at"] == new_starts

    @pytest.mark.asyncio
    async def test_create_cancel_verify(self) -> None:
        user, patient_id = await _make_org_user_patient()

        async with session_factory() as session:
            tools = BookingTools(session=session, user=user)

            # CREATE
            created = await tools.book_appointment(patient_id, _future(27), "Cancel lifecycle")
            appt_id = created["id"]

            # CANCEL
            cancelled = await tools.cancel_appointment(appt_id)
            assert cancelled["status"] == "cancelled"

            # VERIFY
            db_item = await session.get(Appointment, appt_id)
            assert db_item.status == "cancelled"

    @pytest.mark.asyncio
    async def test_lifecycle_with_availability_verification(self) -> None:
        """
        CREATE → verify slot occupied → CANCEL → verify slot freed → CREATE again
        All verified against the real DB.
        """
        user, patient_id = await _make_org_user_patient()
        starts_at = _future(28, hour=11)

        async with session_factory() as session:
            tools = BookingTools(session=session, user=user)

            # CREATE
            created = await tools.book_appointment(patient_id, starts_at, "Lifecycle avail")
            appt_id = created["id"]

            # VERIFY SLOT OCCUPIED via tool
            slots_after_create = await tools.get_available_slots(starts_at.date().isoformat())
            assert starts_at.isoformat() not in slots_after_create

            # CANCEL
            await tools.cancel_appointment(appt_id)

            # VERIFY SLOT FREED via tool
            slots_after_cancel = await tools.get_available_slots(starts_at.date().isoformat())
            assert starts_at.isoformat() in slots_after_cancel

            # CREATE AGAIN (slot now free)
            created_2 = await tools.book_appointment(patient_id, starts_at, "Lifecycle avail 2")
            assert created_2["id"] != appt_id

            # VERIFY IN DB
            db_2 = await session.get(Appointment, created_2["id"])
            assert db_2 is not None
            assert db_2.patient_id == patient_id
            assert _dt(db_2.starts_at) == _dt(starts_at)
            assert db_2.status == "confirmed"
