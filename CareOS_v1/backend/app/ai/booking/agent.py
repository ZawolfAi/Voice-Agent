from uuid import UUID

from fastapi import HTTPException

from app.ai.booking.state import BookingState, update_missing_fields
from app.ai.booking.tools import BookingTools

class BookingAgent:
    """Controls the booking workflow using conversation state."""

    def process(
        self,
        state: BookingState,
        *,
        confirmation: str = "unknown",
        new_action: str = "unknown",
    ) -> BookingState:
        if state.error:
            state.status = "failed"
            return state

        # We are waiting for the user to confirm/reject the current operation.
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

            # User wants a different operation.
            if new_action in {"book", "modify", "cancel"}:
                state.action = new_action
                state.awaiting_confirmation = False
                state.status = "collecting"
                update_missing_fields(state)
                return state

            # We don't understand what the user wants.
            return state

        # Normal workflow.
        update_missing_fields(state)

        if state.missing_fields:
            if state.missing_fields == ["available_slots"]:
                state.status = "executing"
                state.awaiting_confirmation = False
                return state

            state.status = "collecting"
            state.awaiting_confirmation = False
            return state

        state.status = "confirming"
        state.awaiting_confirmation = True
        return state

    async def execute(
        self,
        state: BookingState,
        tools: BookingTools,
    ) -> BookingState:
        if state.status != "executing":
            state.error = "Agent is not ready for execution."
            state.status = "failed"
            return state

        try:
            from datetime import datetime
            if state.action == "book":
                if state.target_date and state.available_slots is None:
                    slots = await tools.get_available_slots(state.target_date)
                    state.available_slots = slots
                    if not slots:
                        state.error = "No available slots for this date."
                        state.status = "failed"
                        return state
                    
                if state.starts_at and state.available_slots is not None:
                    if state.starts_at.isoformat() not in state.available_slots:
                        state.starts_at = None
                        state.status = "collecting"
                        update_missing_fields(state)
                        state.missing_fields.insert(0, "unavailable_choice")
                        return state

                starts_at = state.starts_at
                if not starts_at and state.selected_slot:
                    if state.available_slots and state.selected_slot not in state.available_slots:
                        state.selected_slot = None
                        state.status = "collecting"
                        update_missing_fields(state)
                        state.missing_fields.insert(0, "unavailable_choice")
                        return state
                    try:
                        starts_at = datetime.fromisoformat(state.selected_slot)
                    except ValueError:
                        state.error = "Invalid slot format."
                        state.status = "failed"
                        return state

                if not starts_at:
                    state.status = "collecting"
                    update_missing_fields(state)
                    return state

                result = await tools.book_appointment(
                    patient_id=UUID(state.patient_id),
                    starts_at=starts_at,
                    reason=state.reason,
                )

            elif state.action == "modify":
                result = await tools.modify_appointment(
                    appointment_id=UUID(state.appointment_id),
                    starts_at=state.starts_at,
                    reason=state.reason,
                )

            elif state.action == "cancel":
                result = await tools.cancel_appointment(
                    appointment_id=UUID(state.appointment_id),
                )

            else:
                state.status = "failed"
                state.error = "Unsupported booking action."
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
