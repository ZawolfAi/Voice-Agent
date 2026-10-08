"""End-to-End Integration test simulating CareOS backend on /api/v1/assistant/chat."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
import httpx

from voice_agent.app.agent.state import new_conversation
from voice_agent.app.agent.voice_agent import VoiceAgent
from voice_agent.app.llm.demo_provider import DemoProvider
from voice_agent.app.orchestration.booking_contract import CareOSContract
from voice_agent.app.orchestration.http_client import HTTPOrchestratorClient
from voice_agent.app.schemas.auth import AuthenticatedUserContext
from voice_agent.app.schemas.responses import ResponseStatus


def create_mock_careos_app() -> FastAPI:
    """Mock CareOS application implementing endpoints from api-endpoints.md."""
    app = FastAPI(title="Mock CareOS Backend")

    @app.post("/api/v1/assistant/chat", status_code=200)
    async def chat(request: Request):
        body = await request.json()
        
        message = body.get("message", "").lower()
        patient_id = body.get("patient_id")
        
        if "conflict" in message:
            return JSONResponse(
                status_code=409,
                content={"detail": "Schedule conflict"},
            )

        return {
            "answer": f"Confirmed appointment for {patient_id}",
            "intent": "booking",
            "status": "success",
            "active_agent": "booking",
            "conversation_id": body.get("conversation_id") or "conv-123",
            "patient_id": patient_id,
            "orchestrator_state": {"step": "completed"},
        }

    return app


@pytest.mark.asyncio
async def test_careos_e2e_booking_success() -> None:
    mock_careos = create_mock_careos_app()
    transport = httpx.ASGITransport(app=mock_careos)

    contract = CareOSContract(token="careos-secret-token-123")
    orchestrator = HTTPOrchestratorClient(
        base_url="http://testserver/api/v1",
        contract=contract,
        timeout_seconds=5.0,
        transport=transport,
    )

    llm = DemoProvider()
    agent = VoiceAgent(orchestrator=orchestrator, llm_provider=llm)

    state = new_conversation(authenticated_user=AuthenticatedUserContext(patient_id="11111111-1111-1111-1111-111111111111"))

    reply, state = await agent.handle_text(
        "I would like to book an appointment tomorrow at 2 PM",
        state,
    )

    assert "Confirmed appointment" in reply
    assert state.last_agent_response is not None
    assert state.last_agent_response.status == ResponseStatus.SUCCESS
    assert state.conversation_id == "conv-123"
    assert state.orchestrator_state == {"step": "completed"}


@pytest.mark.asyncio
async def test_careos_e2e_schedule_conflict() -> None:
    mock_careos = create_mock_careos_app()
    transport = httpx.ASGITransport(app=mock_careos)

    contract = CareOSContract(token="careos-secret-token-123")
    orchestrator = HTTPOrchestratorClient(
        base_url="http://testserver/api/v1",
        contract=contract,
        timeout_seconds=5.0,
        transport=transport,
    )

    llm = DemoProvider()
    agent = VoiceAgent(orchestrator=orchestrator, llm_provider=llm)

    state = new_conversation(authenticated_user=AuthenticatedUserContext(patient_id="22222222-2222-2222-2222-222222222222"))
    reply, state = await agent.handle_text(
        "I want an appointment with conflict",
        state,
    )

    assert "conflict" in reply.lower() or "تعارض" in reply.lower()

