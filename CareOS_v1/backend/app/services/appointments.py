from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import write_audit
from app.models import Appointment, ReminderJob


VALID_NEW_STATUSES = {"pending", "confirmed"}
VALID_STATUSES = {"pending", "confirmed", "arrived", "cancelled"}


def appointment_public(item: Appointment) -> dict[str, object]:
    return {
        "id": item.id,
        "patient_id": item.patient_id,
        "starts_at": item.starts_at,
        "reason": item.reason,
        "status": item.status,
        "reminder_status": item.reminder_status,
    }


async def create_appointment(
    session: AsyncSession,
    *,
    organization_id: UUID,
    patient_id: UUID,
    starts_at: datetime,
    reason: str,
    status: str,
    user,
) -> dict[str, object]:
    from app.api import ensure_patient_access

    await ensure_patient_access(session, patient_id, user, "appointments")
    if starts_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Appointment must be scheduled in the future")
    if status not in VALID_NEW_STATUSES:
        raise HTTPException(status_code=422, detail="New appointments must be pending or confirmed")

    conflict = await session.scalar(
        select(Appointment).where(
            Appointment.organization_id == organization_id,
            Appointment.starts_at == starts_at,
            Appointment.status.not_in(["cancelled"]),
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="An appointment already exists at this time")

    item = Appointment(
        organization_id=organization_id,
        patient_id=patient_id,
        starts_at=starts_at,
        reason=reason,
        status=status,
    )
    session.add(item)
    await session.flush()
    session.add(
        ReminderJob(
            organization_id=organization_id,
            appointment_id=item.id,
            scheduled_for=item.starts_at,
            channel="sandbox",
        )
    )
    item.reminder_status = "queued"
    await write_audit(session, user, "appointment.created", str(item.id))
    await session.commit()
    return appointment_public(item)


async def update_appointment_status(
    session: AsyncSession,
    *,
    appointment_id: UUID,
    status: str,
    organization_id: UUID,
    user,
) -> dict[str, object]:
    from app.api import ensure_patient_access

    item = await session.get(Appointment, appointment_id)
    if item is None or item.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    await ensure_patient_access(session, item.patient_id, user, "appointments")
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid appointment status")
    if item.status == "cancelled" and status != "cancelled":
        raise HTTPException(status_code=409, detail="Cancelled appointments cannot be reopened")

    item.status = status
    await write_audit(session, user, "appointment.status_updated", str(item.id))
    await session.commit()
    return appointment_public(item)


async def reschedule_appointment(
    session: AsyncSession,
    *,
    appointment_id: UUID,
    organization_id: UUID,
    starts_at: datetime | None,
    reason: str | None,
    user,
) -> dict[str, object]:
    from app.api import ensure_patient_access

    item = await session.get(Appointment, appointment_id)
    if item is None or item.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    await ensure_patient_access(session, item.patient_id, user, "appointments")
    if item.status == "cancelled":
        raise HTTPException(status_code=409, detail="Cancelled appointments cannot be rescheduled")

    if starts_at is not None:
        if starts_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="Appointment must be scheduled in the future")
        conflict = await session.scalar(
            select(Appointment).where(
                Appointment.organization_id == organization_id,
                Appointment.id != item.id,
                Appointment.starts_at == starts_at,
                Appointment.status.not_in(["cancelled"]),
            )
        )
        if conflict:
            raise HTTPException(status_code=409, detail="An appointment already exists at this time")
        item.starts_at = starts_at
        item.reminder_status = "queued"

    if reason is not None:
        item.reason = reason

    await write_audit(session, user, "appointment.rescheduled", str(item.id))
    await session.commit()
    return appointment_public(item)


async def get_available_slots(
    session: AsyncSession,
    *,
    organization_id: UUID,
    target_date: date,
) -> list[datetime]:
    today = datetime.now(timezone.utc).date()
    if target_date < today:
        raise HTTPException(status_code=400, detail="Cannot request availability for past dates")

    day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    start_time = day_start.replace(hour=9, minute=0)
    end_time = day_start.replace(hour=17, minute=0)

    now = datetime.now(timezone.utc)
    slots: list[datetime] = []
    current = start_time
    while current < end_time:
        if current > now:
            slots.append(current)
        current += timedelta(minutes=30)

    booked_slots = (
        await session.scalars(
            select(Appointment.starts_at).where(
                Appointment.organization_id == organization_id,
                Appointment.starts_at >= day_start,
                Appointment.starts_at < day_end,
                Appointment.status.not_in(["cancelled"]),
            )
        )
    ).all()
    booked = {
        (slot.replace(tzinfo=timezone.utc) if slot.tzinfo is None else slot).isoformat()
        for slot in booked_slots
    }
    return [slot for slot in slots if slot.isoformat() not in booked]
