"""Thin Voice Agent that forwards text to the CareOS Orchestrator."""

from __future__ import annotations

import logging
from datetime import datetime
from time import perf_counter
from typing import Callable

from voice_agent.app.llm.provider import LLMProvider
from voice_agent.app.orchestration.client import OrchestratorClient
from voice_agent.app.orchestration.http_client import OrchestratorBusinessError
from voice_agent.app.schemas.requests import AgentRequest, ConversationState
from voice_agent.app.schemas.responses import AgentResponse, ResponseStatus

logger = logging.getLogger(__name__)


class VoiceAgent:
    def __init__(
        self,
        orchestrator: OrchestratorClient,
        llm_provider: LLMProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._llm_provider = llm_provider
        self._clock = clock or (lambda: datetime.now().astimezone())

    async def handle_text(
        self, text: str, state: ConversationState
    ) -> tuple[str, ConversationState]:
        """Forward a text turn to the Orchestrator and update state."""
        if not text.strip():
            return "I didn't catch that. Could you please repeat your request?", state

        request = AgentRequest(
            session_id=state.session_id,
            patient_id=state.patient_id,
            message=text,
            conversation_id=state.conversation_id,
            orchestrator_state=state.orchestrator_state,
        )
        state.previous_actions.append(request)

        started = perf_counter()
        try:
            response = await self._orchestrator.submit(request)
        except OrchestratorBusinessError as exc:
            return str(exc) or "The requested action could not be completed.", state
        except Exception as exc:
            logger.warning(
                "voice_agent.orchestrator.failed",
                extra={
                    "request_id": str(request.request_id),
                    "session_id": str(state.session_id),
                    "outcome": "failure",
                    "error_type": type(exc).__name__,
                    "latency_ms": round((perf_counter() - started) * 1000),
                },
            )
            return "I couldn't reach the healthcare platform just now. Please try again later.", state

        state.last_agent_response = response
        state.conversation_id = response.conversation_id
        state.orchestrator_state = response.orchestrator_state
        if response.intent:
            state.current_intent = response.intent

        logger.info(
            "voice_agent.orchestrator.completed",
            extra={
                "request_id": str(request.request_id),
                "session_id": str(state.session_id),
                "outcome": response.status.value,
                "latency_ms": round((perf_counter() - started) * 1000),
            },
        )
        return self._render_response(response), state

    @staticmethod
    def _render_response(response: AgentResponse) -> str:
        if response.status != ResponseStatus.SUCCESS:
            return response.message or "The healthcare platform could not complete that request."

        if response.action == "appointment_options":
            if not response.appointments:
                return "The healthcare platform returned no appointment options."
            options = "; ".join(
                f"{option.doctor} is available at {option.time}"
                for option in response.appointments
            )
            count = len(response.appointments)
            noun = "appointment" if count == 1 else "appointments"
            return f"I found {count} available {noun}: {options}. Which one would you prefer?"

        if response.action == "booking_confirmed":
            return response.message or "The healthcare platform confirmed your booking."
        return response.message or "The healthcare platform returned an update."