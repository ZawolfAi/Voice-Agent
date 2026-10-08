from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import write_audit
from app.models import Appointment, FollowUp, Patient


VALID_STATUSES = {"pending", "completed", "cancelled"}


async def _owned_patient(session: AsyncSession, patient_id: UUID, organization_id: UUID) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None or patient.organization_id != organization_id or patient.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


async def _owned_appointment(
    session: AsyncSession,
    appointment_id: UUID,
    organization_id: UUID,
    patient_id: UUID,
) -> Appointment:
    appointment = await session.get(Appointment, appointment_id)
    if (
        appointment is None
        or appointment.organization_id != organization_id
        or appointment.patient_id != patient_id
    ):
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appointment


def followup_public(item: FollowUp) -> dict[str, object]:
    return {
        "id": item.id,
        "patient_id": item.patient_id,
        "appointment_id": item.appointment_id,
        "followup_type": item.followup_type,
        "reason": item.reason,
        "due_at": item.due_at,
        "status": item.status,
    }


async def create_followup(
    session: AsyncSession,
    *,
    organization_id: UUID,
    patient_id: UUID,
    appointment_id: UUID | None = None,
    followup_type: str,
    reason: str,
    due_at: datetime,
    user,
) -> dict[str, object]:
    await _owned_patient(session, patient_id, organization_id)
    if appointment_id is not None:
        await _owned_appointment(session, appointment_id, organization_id, patient_id)

    if due_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Follow-up must be scheduled in the future")

    item = FollowUp(
        organization_id=organization_id,
        patient_id=patient_id,
        appointment_id=appointment_id,
        followup_type=followup_type,
        reason=reason,
        due_at=due_at,
        status="pending",
    )
    session.add(item)
    await session.flush()
    await write_audit(session, user, "followup.created", str(item.id))
    await session.commit()
    return followup_public(item)


async def get_followup(
    session: AsyncSession,
    *,
    followup_id: UUID,
    organization_id: UUID,
) -> FollowUp:
    item = await session.get(FollowUp, followup_id)
    if item is None or item.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return item


async def update_followup(
    session: AsyncSession,
    *,
    followup_id: UUID,
    organization_id: UUID,
    due_at: datetime | None = None,
    reason: str | None = None,
    user,
) -> dict[str, object]:
    item = await get_followup(session, followup_id=followup_id, organization_id=organization_id)
    if item.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending follow-ups can be updated")

    if due_at is not None:
        if due_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="Follow-up must be scheduled in the future")
        item.due_at = due_at
    if reason is not None:
        item.reason = reason

    await write_audit(session, user, "followup.updated", str(item.id))
    await session.commit()
    return followup_public(item)


async def update_followup_status(
    session: AsyncSession,
    *,
    followup_id: UUID,
    organization_id: UUID,
    status: str,
    user,
) -> dict[str, object]:
    item = await get_followup(session, followup_id=followup_id, organization_id=organization_id)
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid follow-up status")
    if item.status == "cancelled" and status != "cancelled":
        raise HTTPException(status_code=409, detail="Cancelled follow-ups cannot be reopened")
    if item.status == "completed" and status != "completed":
        raise HTTPException(status_code=409, detail="Completed follow-ups cannot be reopened")

    item.status = status
    await write_audit(session, user, "followup.status_updated", str(item.id))
    await session.commit()
    return followup_public(item)
