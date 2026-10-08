"""Tests for the thin Voice Agent."""

import asyncio
from datetime import datetime, timezone
from typing import Any
import pytest

from voice_agent.app.agent.state import new_conversation
from voice_agent.app.agent.voice_agent import VoiceAgent
from voice_agent.app.llm.demo_provider import DemoProvider
from voice_agent.app.orchestration.client import MockOrchestratorClient
from voice_agent.app.schemas.auth import AuthenticatedUserContext
from voice_agent.app.schemas.requests import AgentRequest
from voice_agent.app.schemas.responses import AgentResponse, ResponseStatus


NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def authenticated_conversation() -> Any:
    return new_conversation(
        AuthenticatedUserContext(patient_id="33333333-3333-3333-3333-333333333333")
    )


class FailingOrchestrator:
    async def submit(self, request: Any) -> Any:
        raise ConnectionError("sensitive request details should not be logged")


def agent_for(orchestrator: Any | None = None) -> tuple[VoiceAgent, Any]:
    mock_orchestrator = orchestrator or MockOrchestratorClient()
    agent = VoiceAgent(
        orchestrator=mock_orchestrator,
        llm_provider=DemoProvider(),  # No longer used
        clock=lambda: NOW,
    )
    return agent, mock_orchestrator


def test_empty_text_handled_gracefully() -> None:
    async def run() -> None:
        agent, orchestrator = agent_for()
        state = authenticated_conversation()
        reply, state = await agent.handle_text("   ", state)
        
        assert "repeat your request" in reply
        assert not hasattr(orchestrator, 'requests') or not orchestrator.requests
        
    asyncio.run(run())


def test_agent_forwards_text_to_orchestrator() -> None:
    async def run() -> None:
        agent, orchestrator = agent_for()
        state = authenticated_conversation()
        
        reply, state = await agent.handle_text("I want to book an appointment", state)
        
        assert len(orchestrator.requests) == 1
        request = orchestrator.requests[0]
        assert request.message == "I want to book an appointment"
        assert request.patient_id == "33333333-3333-3333-3333-333333333333"
        assert state.previous_actions[-1] == request

    asyncio.run(run())


def test_orchestrator_failure_fails_gracefully_without_logging_patient_text(caplog: Any) -> None:
    async def run() -> None:
        agent, _ = agent_for(orchestrator=FailingOrchestrator())
        state = authenticated_conversation()
        reply, _ = await agent.handle_text("check my appointment secret-phrase", state)
        
        assert "try again later" in reply
        assert "secret-phrase" not in caplog.text
        
        failure_records = [
            record for record in caplog.records
            if record.message == "voice_agent.orchestrator.failed"
        ]
        assert failure_records
        assert failure_records[0].error_type == "ConnectionError"

    asyncio.run(run())