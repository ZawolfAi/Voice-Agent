import logging
from typing import Any

from app.ai.booking.agent import BookingAgent
from app.ai.booking.state import BookingState, build_booking_state, update_missing_fields as update_booking_missing
from app.ai.booking.tools import BookingTools
from app.ai.extractor import BookingExtractor
from app.ai.followup.agent import FollowUpAgent
from app.ai.followup.extractor import FollowUpExtractor
from app.ai.followup.state import FollowUpState, build_followup_state, update_missing_fields as update_followup_missing
from app.ai.followup.tools import FollowUpTools
from app.ai.orchestrator.contracts import IntentType, OrchestratorResponse, OrchestratorState
from app.ai.orchestrator.router import IntentRouter

logger = logging.getLogger(__name__)

CLARIFICATION_MESSAGE = (
    "I need a little more information. Are you trying to book an appointment or create/manage a follow-up?"
)


class CareOSOrchestrator:
    """
    CareOS Orchestrator.
    Routes user messages to either BookingAgent or FollowUpAgent based on LLM IntentRouter,
    or returns clarification for unknown intents.
    """

    def __init__(
        self,
        router: IntentRouter | None = None,
        booking_extractor: BookingExtractor | None = None,
        followup_extractor: FollowUpExtractor | None = None,
        booking_agent: BookingAgent | None = None,
        followup_agent: FollowUpAgent | None = None,
    ) -> None:
        self.router = router or IntentRouter()
        self.booking_extractor = booking_extractor or BookingExtractor()
        self.followup_extractor = followup_extractor or FollowUpExtractor()
        self.booking_agent = booking_agent or BookingAgent()
        self.followup_agent = followup_agent or FollowUpAgent()

    async def process(
        self,
        user_text: str,
        *,
        patient_id: str | None = None,
        conversation_id: str | None = None,
        state: OrchestratorState | None = None,
        booking_tools: BookingTools | None = None,
        followup_tools: FollowUpTools | None = None,
    ) -> OrchestratorResponse:
        orch_state = state or OrchestratorState(
            patient_id=patient_id,
            conversation_id=conversation_id,
            raw_text=user_text,
        )
        if patient_id:
            orch_state.patient_id = patient_id
        if conversation_id:
            orch_state.conversation_id = conversation_id
        orch_state.raw_text = user_text

        # Classify intent via router LLM
        intent_res = await self.router.classify(user_text)
        intent = intent_res.intent

        # If user is in an active multi-turn conversation and intent was classified as unknown,
        # fallback to the active agent if applicable (e.g. user answering a prompt like "confirm" or "tomorrow")
        if intent == IntentType.UNKNOWN and orch_state.active_agent:
            if orch_state.active_agent == "booking" and orch_state.booking_state:
                intent = IntentType.BOOKING
            elif orch_state.active_agent == "followup" and orch_state.followup_state:
                intent = IntentType.FOLLOWUP

        orch_state.intent = intent

        # ROUTE 1: BOOKING AGENT
        if intent == IntentType.BOOKING:
            return await self._handle_booking(
                user_text=user_text,
                orch_state=orch_state,
                booking_tools=booking_tools,
            )

        # ROUTE 2: FOLLOWUP AGENT
        if intent == IntentType.FOLLOWUP:
            return await self._handle_followup(
                user_text=user_text,
                orch_state=orch_state,
                followup_tools=followup_tools,
            )

        # ROUTE 3: UNKNOWN INTENT (CLARIFICATION)
        orch_state.status = "clarification"
        orch_state.result = {"message": CLARIFICATION_MESSAGE}

        return OrchestratorResponse(
            conversation_id=orch_state.conversation_id,
            patient_id=orch_state.patient_id,
            intent=IntentType.UNKNOWN,
            status="clarification",
            active_agent=None,
            message=CLARIFICATION_MESSAGE,
            booking_agent_called=False,
            followup_agent_called=False,
            orchestrator_state=orch_state,
            result=orch_state.result,
        )

    async def _handle_booking(
        self,
        user_text: str,
        orch_state: OrchestratorState,
        booking_tools: BookingTools | None,
    ) -> OrchestratorResponse:
        orch_state.active_agent = "booking"
        extraction = await self.booking_extractor.extract(user_text)

        b_state = orch_state.booking_state
        if b_state is None:
            b_state = build_booking_state(
                extraction,
                patient_id=orch_state.patient_id,
                conversation_id=orch_state.conversation_id,
            )
        else:
            # Update existing state with newly extracted details
            if extraction.action != "unknown":
                b_state.action = extraction.action
            if extraction.specialty:
                b_state.specialty = extraction.specialty
            if extraction.reason:
                b_state.reason = extraction.reason
            if extraction.appointment_id:
                b_state.appointment_id = extraction.appointment_id
            if extraction.date:
                temp_state = build_booking_state(extraction, patient_id=orch_state.patient_id)
                if temp_state.target_date:
                    b_state.target_date = temp_state.target_date
                if temp_state.starts_at:
                    b_state.starts_at = temp_state.starts_at

        # Pass state to BookingAgent
        b_state = self.booking_agent.process(
            b_state,
            confirmation=extraction.confirmation,
            new_action=extraction.action,
        )

        # Execute tools if ready
        if b_state.status == "executing" and booking_tools is not None:
            b_state = await self.booking_agent.execute(b_state, booking_tools)

        orch_state.booking_state = b_state
        orch_state.status = b_state.status
        orch_state.result = b_state.result
        orch_state.error = b_state.error

        message = ""
        if b_state.status == "collecting":
            if "unavailable_choice" in b_state.missing_fields:
                slots = b_state.available_slots or []
                message = f"The requested time is unavailable. Available slots are: {', '.join(slots)}. Please choose one."
            else:
                message = f"Please provide missing details: {', '.join(b_state.missing_fields)}"
        elif b_state.status == "confirming":
            message = f"Please confirm {b_state.action} appointment."
        elif b_state.status == "completed":
            message = "Booking operation completed successfully."
        elif b_state.status == "failed":
            message = b_state.error or "Booking operation failed."

        return OrchestratorResponse(
            conversation_id=orch_state.conversation_id,
            patient_id=orch_state.patient_id,
            intent=IntentType.BOOKING,
            status=b_state.status,
            active_agent="booking",
            message=message,
            booking_agent_called=True,
            followup_agent_called=False,
            orchestrator_state=orch_state,
            result=b_state.result,
            error=b_state.error,
        )

    async def _handle_followup(
        self,
        user_text: str,
        orch_state: OrchestratorState,
        followup_tools: FollowUpTools | None,
    ) -> OrchestratorResponse:
        orch_state.active_agent = "followup"
        extraction = await self.followup_extractor.extract(user_text)

        f_state = orch_state.followup_state
        if f_state is None:
            f_state = build_followup_state(
                extraction,
                patient_id=orch_state.patient_id,
                conversation_id=orch_state.conversation_id,
            )
        else:
            if extraction.action != "unknown":
                f_state.action = extraction.action
            if extraction.followup_type:
                f_state.followup_type = extraction.followup_type
            if extraction.reason:
                f_state.reason = extraction.reason
            if extraction.followup_id:
                f_state.followup_id = extraction.followup_id
            if extraction.appointment_id:
                f_state.appointment_id = extraction.appointment_id
            if extraction.date:
                temp_state = build_followup_state(extraction, patient_id=orch_state.patient_id)
                if temp_state.target_date:
                    f_state.target_date = temp_state.target_date
                if temp_state.due_at:
                    f_state.due_at = temp_state.due_at

        # Pass state to FollowUpAgent
        f_state = self.followup_agent.process(
            f_state,
            confirmation=extraction.confirmation,
            new_action=extraction.action,
        )

        # Execute tools if ready
        if f_state.status == "executing" and followup_tools is not None:
            f_state = await self.followup_agent.execute(f_state, followup_tools)

        orch_state.followup_state = f_state
        orch_state.status = f_state.status
        orch_state.result = f_state.result
        orch_state.error = f_state.error

        message = ""
        if f_state.status == "collecting":
            message = f"Please provide missing details: {', '.join(f_state.missing_fields)}"
        elif f_state.status == "confirming":
            message = f"Please confirm {f_state.action} followup."
        elif f_state.status == "completed":
            message = "Followup operation completed successfully."
        elif f_state.status == "failed":
            message = f_state.error or "Followup operation failed."

        return OrchestratorResponse(
            conversation_id=orch_state.conversation_id,
            patient_id=orch_state.patient_id,
            intent=IntentType.FOLLOWUP,
            status=f_state.status,
            active_agent="followup",
            message=message,
            booking_agent_called=False,
            followup_agent_called=True,
            orchestrator_state=orch_state,
            result=f_state.result,
            error=f_state.error,
        )
