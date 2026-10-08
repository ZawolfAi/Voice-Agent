from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api import ensure_patient_access
from app.services.followups import (
    create_followup,
    get_followup,
    update_followup,
    update_followup_status,
    followup_public,
)

class FollowUpTools:
    """Thin adapter between the FollowUp Agent and followup services."""

    def __init__(self, session: AsyncSession, user) -> None:
        self.session = session
        self.user = user

    async def create_followup(
        self,
        patient_id: UUID,
        followup_type: str,
        reason: str,
        due_at: datetime,
        appointment_id: UUID | None = None,
    ) -> dict[str, object]:
        await ensure_patient_access(
            self.session,
            patient_id,
            self.user,
            "appointments",
        )
        return await create_followup(
            session=self.session,
            organization_id=self.user.organization_id,
            patient_id=patient_id,
            appointment_id=appointment_id,
            followup_type=followup_type,
            reason=reason,
            due_at=due_at,
            user=self.user,
        )

    async def get_followup(self, followup_id: UUID) -> dict[str, object]:
        item = await get_followup(
            self.session,
            followup_id=followup_id,
            organization_id=self.user.organization_id,
        )
        await ensure_patient_access(self.session, item.patient_id, self.user, "appointments")
        return followup_public(item)

    async def update_followup(
        self,
        followup_id: UUID,
        due_at: datetime | None = None,
        reason: str | None = None,
    ) -> dict[str, object]:
        item = await get_followup(self.session, followup_id=followup_id, organization_id=self.user.organization_id)
        await ensure_patient_access(self.session, item.patient_id, self.user, "appointments")

        return await update_followup(
            session=self.session,
            followup_id=followup_id,
            organization_id=self.user.organization_id,
            due_at=due_at,
            reason=reason,
            user=self.user,
        )

    async def update_followup_status(
        self,
        followup_id: UUID,
        status: str,
    ) -> dict[str, object]:
        item = await get_followup(self.session, followup_id=followup_id, organization_id=self.user.organization_id)
        await ensure_patient_access(self.session, item.patient_id, self.user, "appointments")
        
        return await update_followup_status(
            session=self.session,
            followup_id=followup_id,
            organization_id=self.user.organization_id,
            status=status,
            user=self.user,
        )
