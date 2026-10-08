from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from app.ai.booking.state import BookingState
from app.ai.followup.state import FollowUpState


class IntentType(str, Enum):
    BOOKING = "booking"
    FOLLOWUP = "followup"
    UNKNOWN = "unknown"


class IntentResult(BaseModel):
    intent: IntentType = IntentType.UNKNOWN


class OrchestratorState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    conversation_id: str | None = None
    patient_id: str | None = None
    raw_text: str = ""
    intent: IntentType = IntentType.UNKNOWN
    status: str = "new"
    active_agent: Literal["booking", "followup"] | None = None
    booking_state: BookingState | None = None
    followup_state: FollowUpState | None = None
    result: Any | None = None
    error: str | None = None


class OrchestratorResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    conversation_id: str | None = None
    patient_id: str | None = None
    intent: IntentType = IntentType.UNKNOWN
    status: str = "completed"
    active_agent: str | None = None
    message: str = ""
    booking_agent_called: bool = False
    followup_agent_called: bool = False
    orchestrator_state: OrchestratorState | None = None
    result: Any | None = None
    error: str | None = None
