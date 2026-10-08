"""Structured requests and conversation state for agent communication."""

from __future__ import annotations

from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from voice_agent.app.schemas.auth import AuthenticatedUserContext


class Intent(str, Enum):
    BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
    CHECK_APPOINTMENT = "CHECK_APPOINTMENT"
    CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"
    RESCHEDULE_APPOINTMENT = "RESCHEDULE_APPOINTMENT"
    FOLLOW_UP = "FOLLOW_UP"
    GENERAL_QUESTION = "GENERAL_QUESTION"
    EMERGENCY = "EMERGENCY"
    UNKNOWN = "UNKNOWN"


class AgentRequest(BaseModel):
    """Envelope sent by the Voice Agent to the Orchestrator."""

    model_config = ConfigDict(extra="forbid")

    request_id: UUID = Field(default_factory=uuid4)
    source: Literal["voice_agent"] = "voice_agent"
    session_id: UUID | None = None
    patient_id: str | None = None
    message: str = ""
    conversation_id: str | None = None
    orchestrator_state: dict | None = None


class ConversationState(BaseModel):
    """Minimal per-session state; avoid storing unnecessary patient details."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID = Field(default_factory=uuid4)
    authenticated_user: AuthenticatedUserContext | None = None
    current_intent: str | None = None
    collected_parameters: dict[str, str] = Field(default_factory=dict)
    missing_parameters: list[str] = Field(default_factory=list)
    previous_actions: list[AgentRequest] = Field(default_factory=list)
    last_agent_response: "AgentResponse | None" = None
    conversation_id: str | None = None
    orchestrator_state: dict | None = None

    @property
    def patient_id(self) -> str | None:
        """Identity supplied by the trusted host, never from conversation text."""
        return self.authenticated_user.patient_id if self.authenticated_user else None


from .responses import AgentResponse  # noqa: E402  (resolve forward reference)

ConversationState.model_rebuild()