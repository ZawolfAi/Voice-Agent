"""Unit tests for CareOSContract adapter."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from voice_agent.app.orchestration.booking_contract import CareOSContract
from voice_agent.app.orchestration.http_client import (
    OrchestratorAuthenticationError,
    OrchestratorAuthorizationError,
    OrchestratorBusinessError,
    OrchestratorValidationError,
)
from voice_agent.app.schemas.requests import AgentRequest
from voice_agent.app.schemas.responses import ResponseStatus


def test_prepare_assistant_chat() -> None:
    contract = CareOSContract(token="test-jwt-token")
    valid_uuid = str(uuid4())
    request = AgentRequest(
        patient_id=valid_uuid,
        message="I want to book an appointment",
        conversation_id="conv-123",
        orchestrator_state={"step": "booking"},
        session_id=uuid4(),
    )
    prepared = contract.prepare(request)
    assert prepared.method == "POST"
    assert prepared.path == "assistant/chat"
    assert prepared.headers["Authorization"] == "Bearer test-jwt-token"
    assert prepared.headers["Content-Type"] == "application/json"

    data = json.loads(prepared.content.decode("utf-8"))
    assert data["patient_id"] == valid_uuid
    assert data["message"] == "I want to book an appointment"
    assert data["conversation_id"] == "conv-123"
    assert data["orchestrator_state"] == {"step": "booking"}

def test_prepare_missing_patient_id_fails() -> None:
    contract = CareOSContract(token="test-jwt-token")
    request = AgentRequest(
        patient_id=None,
        message="hello",
        session_id=uuid4(),
    )
    with pytest.raises(OrchestratorValidationError, match="A valid patient ID is required"):
        contract.prepare(request)

def test_prepare_invalid_patient_id_fails() -> None:
    contract = CareOSContract(token="test-jwt-token")
    request = AgentRequest(
        patient_id="invalid-id",
        message="hello",
        session_id=uuid4(),
    )
    with pytest.raises(OrchestratorValidationError, match="Invalid patient ID format"):
        contract.prepare(request)


def test_parse_careos_assistant_response() -> None:
    contract = CareOSContract()
    response = httpx.Response(
        status_code=200,
        json={
            "answer": "Your appointment is confirmed.",
            "intent": "booking",
            "status": "success",
            "active_agent": "booking_agent",
            "conversation_id": "conv-123",
            "patient_id": "patient-456",
            "orchestrator_state": {"state": "done"},
        },
    )
    agent_resp = contract.parse_response(response)
    assert agent_resp.status == ResponseStatus.SUCCESS
    assert agent_resp.action == "booking_agent"
    assert agent_resp.message == "Your appointment is confirmed."
    assert agent_resp.conversation_id == "conv-123"
    assert agent_resp.orchestrator_state == {"state": "done"}
    assert agent_resp.intent == "booking"


def test_map_careos_errors() -> None:
    contract = CareOSContract()
    err_401 = contract.map_error(httpx.Response(status_code=401))
    assert isinstance(err_401, OrchestratorAuthenticationError)

    err_409 = contract.map_error(httpx.Response(status_code=409))
    assert isinstance(err_409, OrchestratorBusinessError)

    err_422 = contract.map_error(httpx.Response(status_code=422))
    assert isinstance(err_422, OrchestratorValidationError)
