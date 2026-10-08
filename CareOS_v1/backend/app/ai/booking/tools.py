from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api import ensure_patient_access
from app.services.appointments import (
    create_appointment,
    reschedule_appointment,
    update_appointment_status,
)


class BookingTools:
    """Thin adapter between the Booking Agent and appointment services."""

    def __init__(self, session: AsyncSession, user) -> None:
        self.session = session
        self.user = user

    async def book_appointment(
        self,
        patient_id: UUID,
        starts_at: datetime,
        reason: str,
    ) -> dict[str, object]:
        await ensure_patient_access(
            self.session,
            patient_id,
            self.user,
            "appointments",
        )

        return await create_appointment(
            session=self.session,
            organization_id=self.user.organization_id,
            patient_id=patient_id,
            starts_at=starts_at,
            reason=reason,
            status="confirmed",
            user=self.user,
        )

    async def get_available_slots(self, target_date: str) -> list[str]:
        from datetime import date
        from app.services.appointments import get_available_slots
        
        parsed = date.fromisoformat(target_date)
        slots = await get_available_slots(
            session=self.session,
            organization_id=self.user.organization_id,
            target_date=parsed,
        )
        return [slot.isoformat() for slot in slots]

    async def modify_appointment(
        self,
        appointment_id: UUID,
        starts_at: datetime | None = None,
        reason: str | None = None,
    ) -> dict[str, object]:
        return await reschedule_appointment(
            session=self.session,
            appointment_id=appointment_id,
            organization_id=self.user.organization_id,
            starts_at=starts_at,
            reason=reason,
            user=self.user,
        )

    async def cancel_appointment(
        self,
        appointment_id: UUID,
    ) -> dict[str, object]:
        return await update_appointment_status(
            session=self.session,
            appointment_id=appointment_id,
            status="cancelled",
            organization_id=self.user.organization_id,
            user=self.user,
        )
