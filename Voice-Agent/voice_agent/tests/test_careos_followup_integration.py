"""End-to-End Integration test simulating CareOS Follow-up backend routing."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx

from voice_agent.app.agent.state import new_conversation
from voice_agent.app.agent.voice_agent import VoiceAgent
from voice_agent.app.llm.demo_provider import DemoProvider
from voice_agent.app.orchestration.booking_contract import CareOSContract
from voice_agent.app.orchestration.http_client import HTTPOrchestratorClient
from voice_agent.app.schemas.auth import AuthenticatedUserContext
from voice_agent.app.schemas.responses import ResponseStatus


def create_mock_careos_followup_app() -> FastAPI:
    """Mock CareOS application implementing followup endpoint routing."""
    app = FastAPI(title="Mock CareOS FollowUp")

    @app.post("/api/v1/assistant/chat", status_code=200)
    async def chat(request: Request):
        body = await request.json()
        message = body.get("message", "").lower()
        patient_id = body.get("patient_id")
        
        if "متابعة" in message or "followup" in message:
            return {
                "answer": "تم تسجيل المتابعة",
                "intent": "followup",
                "status": "success",
                "active_agent": "followup",
                "conversation_id": body.get("conversation_id") or "conv-fu-123",
                "patient_id": patient_id,
                "orchestrator_state": {"step": "completed", "agent_states": {"followup": {"status": "completed"}}},
            }
            
        return {
            "answer": "Unknown intent",
            "intent": "unknown",
            "status": "success",
            "active_agent": None,
            "conversation_id": body.get("conversation_id"),
            "patient_id": patient_id,
            "orchestrator_state": {},
        }

    return app


@pytest.mark.asyncio
async def test_careos_e2e_followup_integration_success() -> None:
    mock_careos = create_mock_careos_followup_app()
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
        "عايز أعمل متابعة",
        state,
    )

    assert "تم تسجيل المتابعة" in reply
    assert state.last_agent_response is not None
    assert state.last_agent_response.status == ResponseStatus.SUCCESS
    assert state.conversation_id == "conv-fu-123"
    assert state.orchestrator_state["agent_states"]["followup"]["status"] == "completed"

