"""Typed Orchestrator response models."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ResponseStatus(str, Enum):
    SUCCESS = "success"
    ACCEPTED = "accepted"
    ERROR = "error"
    NOT_CONFIGURED = "not_configured"


class AppointmentOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor: str
    time: str


class AgentResponse(BaseModel):
    """Structured result returned by the Orchestrator."""

    model_config = ConfigDict(extra="forbid")

    status: ResponseStatus
    action: str | None = None
    appointments: list[AppointmentOption] = Field(default_factory=list)
    message: str | None = None
    conversation_id: str | None = None
    orchestrator_state: dict | None = None
    intent: str | None = None