from uuid import UUID
from fastapi import HTTPException

from app.ai.followup.state import FollowUpState, update_missing_fields
from app.ai.followup.tools import FollowUpTools

class FollowUpAgent:
    """Controls the followup workflow using conversation state."""

    def process(
        self,
        state: FollowUpState,
        *,
        confirmation: str = "unknown",
        new_action: str = "unknown",
    ) -> FollowUpState:
        if state.error:
            state.status = "failed"
            return state

        if state.awaiting_confirmation:
            if confirmation == "confirm":
                state.status = "executing"
                state.awaiting_confirmation = False
                return state

            if confirmation == "reject":
                state.status = "new"
                state.awaiting_confirmation = False
                state.result = {"message": "Operation rejected"}
                return state

            if new_action in {"create", "get", "modify", "cancel", "complete"}:
                state.action = new_action
                state.awaiting_confirmation = False
                state.status = "collecting"
                update_missing_fields(state)
                return state

            return state

        update_missing_fields(state)

        if state.missing_fields:
            state.status = "collecting"
            state.awaiting_confirmation = False
            return state

        if state.action == "get":
            state.status = "executing"
            state.awaiting_confirmation = False
            return state

        state.status = "confirming"
        state.awaiting_confirmation = True
        return state

    async def execute(
        self,
        state: FollowUpState,
        tools: FollowUpTools,
    ) -> FollowUpState:
        if state.status != "executing":
            state.error = "Agent is not ready for execution."
            state.status = "failed"
            return state

        try:
            if state.action == "create":
                # State guarantees due_at is set if not in missing_fields
                result = await tools.create_followup(
                    patient_id=UUID(state.patient_id),
                    followup_type=state.followup_type,
                    reason=state.reason,
                    due_at=state.due_at,
                    appointment_id=UUID(state.appointment_id) if state.appointment_id else None,
                )
            elif state.action == "get":
                result = await tools.get_followup(
                    followup_id=UUID(state.followup_id),
                )
            elif state.action == "modify":
                result = await tools.update_followup(
                    followup_id=UUID(state.followup_id),
                    due_at=state.due_at,
                    reason=state.reason,
                )
            elif state.action == "cancel":
                result = await tools.update_followup_status(
                    followup_id=UUID(state.followup_id),
                    status="cancelled",
                )
            elif state.action == "complete":
                result = await tools.update_followup_status(
                    followup_id=UUID(state.followup_id),
                    status="completed",
                )
            else:
                state.status = "failed"
                state.error = "Unsupported followup action."
                return state

            state.result = result
            state.status = "completed"
            state.awaiting_confirmation = False
            return state

        except HTTPException as exc:
            state.status = "failed"
            state.error = exc.detail
            return state
        except ValueError as exc:
            state.status = "failed"
            state.error = str(exc)
            return state
