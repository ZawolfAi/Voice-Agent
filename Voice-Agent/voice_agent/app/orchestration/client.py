"""Orchestrator interface and an explicitly non-production mock client."""

from typing import Protocol

from voice_agent.app.schemas.requests import AgentRequest
from voice_agent.app.schemas.responses import AgentResponse, ResponseStatus


class OrchestratorClient(Protocol):
    async def submit(self, request: AgentRequest) -> AgentResponse:
        """Submit a structured action to the Orchestrator."""

    async def close(self) -> None:
        """Release client resources when applicable."""


class MockOrchestratorClient:
    """Development stub that refuses to invent clinic or appointment data."""

    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    async def submit(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        if "emergency" in request.message.lower():
            return AgentResponse(
                status=ResponseStatus.NOT_CONFIGURED,
                action="emergency_escalation_not_configured",
                message=(
                    "The approved emergency escalation workflow is not configured "
                    "in this prototype. No escalation was confirmed."
                ),
            )
        if "book" in request.message.lower() or "appointment" in request.message.lower():
            return AgentResponse(
                status=ResponseStatus.NOT_CONFIGURED,
                action="clinic_calendar_not_connected",
                message=(
                    "The clinic calendar is not connected, so I can't verify real "
                    "availability or book an appointment. No booking was made."
                ),
            )
        return AgentResponse(
            status=ResponseStatus.NOT_CONFIGURED,
            action="action_not_implemented",
            message="This action is not implemented by the prototype Orchestrator.",
        )

    async def close(self) -> None:
        """The in-memory mock owns no external resources."""
        return None


# Backwards-compatible Phase 2 import; new code should use MockOrchestratorClient.
MockOrchestrator = MockOrchestratorClient