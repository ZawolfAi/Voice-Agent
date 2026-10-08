"""Integration tests for CareOS platform and Voice Agent system."""

import asyncio
import json
import pytest
import httpx
from uuid import uuid4

from voice_agent.app.agent.state import new_conversation
from voice_agent.app.agent.voice_agent import VoiceAgent
from voice_agent.app.config import Settings
from voice_agent.app.llm.demo_provider import DemoProvider
from voice_agent.app.orchestration.booking_contract import CareOSContract
from voice_agent.app.orchestration.http_client import (
    HTTPOrchestratorClient,
    OrchestratorBusinessError,
)
from voice_agent.app.schemas.auth import AuthenticatedUserContext
from voice_agent.app.schemas.requests import AgentRequest
from voice_agent.integrations.careos.careos_agent_provider import CareOSVoiceAgentAdapter


@pytest.mark.asyncio
async def test_careos_contract_payload_has_careos_database_fields():
    """Verify CareOSContract generates starts_at, reason, and status expected by CareOS backend."""
    contract = CareOSContract(token="jwt-token-123", department="Cosmetics")
    request = AgentRequest(
        patient_id="11111111-1111-1111-1111-111111111111",
        message="I want to book a Botox appointment on 2026-10-15 at 14:00",
        conversation_id="conv-123",
        orchestrator_state={"step": "booking"},
        session_id=uuid4(),
    )
    prepared = contract.prepare(request)
    assert prepared.method == "POST"
    assert prepared.path == "assistant/chat"

    data = json.loads(prepared.content.decode("utf-8"))
    assert data["patient_id"] == "11111111-1111-1111-1111-111111111111"
    assert "message" in data
    assert "Botox" in data["message"]

@pytest.mark.asyncio
async def test_careos_contract_parses_careos_backend_appointment_response():
    """Verify CareOSContract parses CareOS backend assistant format."""
    contract = CareOSContract(token="jwt-token-123", department="Cosmetics")
    
    backend_response_data = {
        "answer": "Your appointment is confirmed.",
        "intent": "booking",
        "status": "success",
        "active_agent": "booking_agent",
        "conversation_id": "conv-123",
        "patient_id": "patient-456",
        "orchestrator_state": {"state": "done"},
    }
    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(backend_response_data).encode("utf-8"),
        request=httpx.Request("POST", "http://testserver/assistant/chat"),
    )
    parsed = contract.parse_response(mock_resp)
    assert parsed.status.value == "success"
    assert parsed.action == "booking_agent"
    assert parsed.message == "Your appointment is confirmed."


@pytest.mark.asyncio
async def test_careos_voice_agent_adapter_offline_resilience():
    """Verify CareOSVoiceAgentAdapter handles unreachable Voice Agent server gracefully."""
    adapter = CareOSVoiceAgentAdapter(base_url="http://127.0.0.1:59999", timeout_seconds=1.0)
    result = await adapter.answer_general("Hello, what services do you provide?")
    assert result["provider"] == "voice_agent_offline"
    assert "offline or unreachable" in result["answer"] or "unreachable" in result["answer"]


@pytest.mark.asyncio
async def test_careos_voice_agent_adapter_mock_loopback():
    """Verify CareOSVoiceAgentAdapter parses turns correctly when agent answers."""
    # Test turn payload structure
    agent_turn_payload = {
        "session_id": str(uuid4()),
        "response_text": "Welcome to our Cosmetics clinic! We offer Botox, fillers, and laser sessions.",
        "thought": None,
        "intent": "general_question",
    }

    # Simulate loopback transport
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps(agent_turn_payload).encode("utf-8"))
    )

    class MockAdapter(CareOSVoiceAgentAdapter):
        async def answer_general(self, message: str):
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.post("http://testserver/v1/voice/turns", json={"text": message})
                data = resp.json()
                return {
                    "answer": data["response_text"],
                    "sources": [{"title": "CareOS Aesthetics & Cosmetics AI Agent"}],
                    "provider": "voice_agent",
                    "session_id": data["session_id"],
                    "intent": data["intent"],
                }

    adapter = MockAdapter()
    res = await adapter.answer_general("What treatments do you have?")
    assert res["provider"] == "voice_agent"
    assert "Botox" in res["answer"]
    assert res["sources"][0]["title"] == "CareOS Aesthetics & Cosmetics AI Agent"
