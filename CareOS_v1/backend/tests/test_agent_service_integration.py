from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.booking.tools import BookingTools
from app.ai.followup.tools import FollowUpTools
from app.db import session_factory
from app.main import app
from app.models import Appointment, FollowUp, ReminderJob, User


def _register_user(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"agent-service-{uuid4().hex[:8]}@example.org",
            "password": "strong-password",
            "full_name": "Agent Service User",
            "organization_name": f"Agent Service Org {uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_patient(client: TestClient, token: str) -> UUID:
    response = client.post(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "medical_record_number": f"AS-{uuid4().hex[:8]}",
            "given_name": "Agent",
            "family_name": "Patient",
            "date_of_birth": "1990-01-01",
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def _load_user(user_id: str) -> User:
    async with session_factory() as session:
        user = await session.get(User, UUID(user_id))
        assert user is not None
        return user


@pytest.mark.asyncio
async def test_booking_tools_create_reschedule_cancel_and_reject_occupied_slot() -> None:
    with TestClient(app) as client:
        registered = _register_user(client)
        patient_id = _create_patient(client, registered["access_token"])

    user = await _load_user(registered["user"]["id"])
    async with session_factory() as session:
        tools = BookingTools(session=session, user=user)
        starts_at = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)

        created = await tools.book_appointment(
            patient_id=patient_id,
            starts_at=starts_at,
            reason="Initial booking",
        )
        appointment_id = created["id"]

        db_item = await session.get(Appointment, appointment_id)
        assert db_item is not None
        assert db_item.patient_id == patient_id
        assert created["status"] == "confirmed"
        reminder = await session.scalar(
            select(ReminderJob).where(ReminderJob.appointment_id == appointment_id)
        )
        assert reminder is not None
        assert reminder.status == "queued"

        target_date = starts_at.date().isoformat()
        available_slots_before_reschedule = await tools.get_available_slots(target_date)
        assert len(available_slots_before_reschedule) >= 2
        rescheduled_at = datetime.fromisoformat(available_slots_before_reschedule[0])
        rescheduled = await tools.modify_appointment(
            appointment_id=appointment_id,
            starts_at=rescheduled_at,
            reason="Updated reason",
        )
        assert rescheduled["starts_at"] == rescheduled_at
        assert rescheduled["reason"] == "Updated reason"

        occupied = await tools.book_appointment(
            patient_id=patient_id,
            starts_at=datetime.fromisoformat(available_slots_before_reschedule[1]),
            reason="Occupy slot",
        )
        with pytest.raises(HTTPException) as error:
            await tools.modify_appointment(
                appointment_id=appointment_id,
                starts_at=occupied["starts_at"],
            )
        assert error.value.status_code == 409

        available_slots = await tools.get_available_slots(occupied["starts_at"].date().isoformat())
        assert occupied["starts_at"].isoformat() not in available_slots

        cancelled = await tools.cancel_appointment(appointment_id=appointment_id)
        assert cancelled["status"] == "cancelled"
        available_slots_after_cancel = await tools.get_available_slots(rescheduled_at.date().isoformat())
        assert rescheduled_at.isoformat() in available_slots_after_cancel

        with pytest.raises(HTTPException) as past_error:
            await tools.get_available_slots((datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat())
        assert past_error.value.status_code == 400


@pytest.mark.asyncio
async def test_followup_tools_create_read_update_and_status() -> None:
    with TestClient(app) as client:
        registered = _register_user(client)
        patient_id = _create_patient(client, registered["access_token"])

    user = await _load_user(registered["user"]["id"])
    async with session_factory() as session:
        booking_tools = BookingTools(session=session, user=user)
        followup_tools = FollowUpTools(session=session, user=user)
        appointment = await booking_tools.book_appointment(
            patient_id=patient_id,
            starts_at=(datetime.now(timezone.utc) + timedelta(days=4)).replace(microsecond=0),
            reason="Follow-up source appointment",
        )
        due_at = (datetime.now(timezone.utc) + timedelta(days=5)).replace(microsecond=0)

        created = await followup_tools.create_followup(
            patient_id=patient_id,
            followup_type="call",
            reason="Check symptoms",
            due_at=due_at,
            appointment_id=appointment["id"],
        )
        followup_id = created["id"]
        assert created["status"] == "pending"
        assert created["followup_type"] == "call"
        assert created["appointment_id"] == appointment["id"]

        db_item = await session.get(FollowUp, followup_id)
        assert db_item is not None
        assert db_item.patient_id == patient_id
        assert db_item.appointment_id == appointment["id"]
        assert db_item.reason == "Check symptoms"

        fetched = await followup_tools.get_followup(followup_id=followup_id)
        assert fetched["id"] == followup_id
        assert fetched["reason"] == "Check symptoms"

        updated_due_at = due_at + timedelta(days=2)
        updated = await followup_tools.update_followup(
            followup_id=followup_id,
            due_at=updated_due_at,
            reason="Check symptoms again",
        )
        assert updated["due_at"] == updated_due_at
        assert updated["reason"] == "Check symptoms again"

        completed = await followup_tools.update_followup_status(
            followup_id=followup_id,
            status="completed",
        )
        assert completed["status"] == "completed"


@pytest.mark.asyncio
async def test_agent_tools_enforce_patient_authorization() -> None:
    with TestClient(app) as client:
        owner_a = _register_user(client)
        patient_a = _create_patient(client, owner_a["access_token"])
        owner_b = _register_user(client)

    user_b = await _load_user(owner_b["user"]["id"])
    async with session_factory() as session:
        booking_tools = BookingTools(session=session, user=user_b)
        with pytest.raises(HTTPException) as booking_error:
            await booking_tools.book_appointment(
                patient_id=patient_a,
                starts_at=datetime.now(timezone.utc) + timedelta(days=3),
                reason="Cross-org booking",
            )
        assert booking_error.value.status_code == 404

        followup_tools = FollowUpTools(session=session, user=user_b)
        with pytest.raises(HTTPException) as followup_error:
            await followup_tools.create_followup(
                patient_id=patient_a,
                followup_type="call",
                reason="Cross-org follow-up",
                due_at=datetime.now(timezone.utc) + timedelta(days=3),
            )
        assert followup_error.value.status_code == 404
