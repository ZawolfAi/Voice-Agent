import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.ai.orchestrator.contracts import IntentType, OrchestratorResponse, OrchestratorState


def test_assistant_chat_unauthenticated() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/assistant/chat", json={"message": "Hello"})
    assert response.status_code == 401


def test_assistant_query_unauthenticated() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/assistant/query",
        json={"patient_id": str(uuid4()), "question": "Patient history"},
    )
    assert response.status_code == 401


@patch("app.ai.orchestrator.orchestrator.CareOSOrchestrator.process")
def test_assistant_chat_authenticated_calls_orchestrator(mock_process, monkeypatch) -> None:
    client = TestClient(app)
    # Register / login a user
    email = f"user-{uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Test Hospital",
            "full_name": "Test Doctor",
            "email": email,
            "password": "Password123!",
            "department": "Cardiology",
            "project": "Default",
        },
    )
    assert reg_resp.status_code == 201
    token = reg_resp.json()["access_token"]

    mock_process.return_value = OrchestratorResponse(
        message="Orchestrator general chat response",
        intent=IntentType.UNKNOWN,
        status="completed",
        active_agent="GeneralAssistant",
        conversation_id="conv-123",
    )

    response = client.post(
        "/api/v1/assistant/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "What are clinic hours?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Orchestrator general chat response"
    assert data["intent"] == "unknown"
    assert data["status"] == "completed"
    assert data["active_agent"] == "GeneralAssistant"
    assert data["conversation_id"] == "conv-123"
    assert mock_process.called


@patch("app.ai.orchestrator.orchestrator.CareOSOrchestrator.process")
def test_assistant_query_authenticated_calls_orchestrator(mock_process) -> None:
    client = TestClient(app)
    email = f"user-{uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Query Hospital",
            "full_name": "Query Doctor",
            "email": email,
            "password": "Password123!",
            "department": "General",
            "project": "Default",
        },
    )
    token = reg_resp.json()["access_token"]

    # Create a patient for this org
    pat_resp = client.post(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "medical_record_number": f"MRN-{uuid4().hex[:6]}",
            "given_name": "John",
            "family_name": "Doe",
            "department": "General",
            "project": "Default",
            "date_of_birth": "1990-01-01",
        },
    )
    assert pat_resp.status_code == 201
    patient_id = pat_resp.json()["id"]

    mock_process.return_value = OrchestratorResponse(
        message="Query answer from Orchestrator",
        intent=IntentType.UNKNOWN,
        status="completed",
        active_agent="GeneralAssistant",
        conversation_id="conv-query-1",
        patient_id=patient_id,
    )

    response = client.post(
        "/api/v1/assistant/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"patient_id": patient_id, "question": "What is patient condition?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Query answer from Orchestrator"
    assert data["intent"] == "unknown"
    assert data["patient_id"] == patient_id
    assert mock_process.called


@patch("app.ai.orchestrator.orchestrator.CareOSOrchestrator.process")
def test_assistant_booking_routing(mock_process) -> None:
    client = TestClient(app)
    email = f"user-{uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Booking Hospital",
            "full_name": "Reception Doctor",
            "email": email,
            "password": "Password123!",
            "department": "Reception",
            "project": "Default",
        },
    )
    token = reg_resp.json()["access_token"]

    mock_process.return_value = OrchestratorResponse(
        message="Which specialty do you need?",
        intent=IntentType.BOOKING,
        status="collecting_info",
        active_agent="BookingAgent",
        conversation_id="conv-book-1",
    )

    response = client.post(
        "/api/v1/assistant/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "I want to book an appointment"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "booking"
    assert data["active_agent"] == "BookingAgent"
    assert data["status"] == "collecting_info"
    assert "specialty" in data["answer"].lower()


@patch("app.ai.orchestrator.orchestrator.CareOSOrchestrator.process")
def test_assistant_followup_routing(mock_process) -> None:
    client = TestClient(app)
    email = f"user-{uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Followup Hospital",
            "full_name": "Followup Doctor",
            "email": email,
            "password": "Password123!",
            "department": "General",
            "project": "Default",
        },
    )
    token = reg_resp.json()["access_token"]

    mock_process.return_value = OrchestratorResponse(
        message="Follow-up scheduled for patient.",
        intent=IntentType.FOLLOWUP,
        status="completed",
        active_agent="FollowUpAgent",
        conversation_id="conv-fol-1",
    )

    response = client.post(
        "/api/v1/assistant/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Schedule a follow-up for patient next week"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "followup"
    assert data["active_agent"] == "FollowUpAgent"


@patch("app.ai.orchestrator.orchestrator.CareOSOrchestrator.process")
def test_llm_failure_response(mock_process) -> None:
    client = TestClient(app)
    email = f"user-{uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Error Hospital",
            "full_name": "Error Doctor",
            "email": email,
            "password": "Password123!",
            "department": "General",
            "project": "Default",
        },
    )
    token = reg_resp.json()["access_token"]

    mock_process.return_value = OrchestratorResponse(
        message="",
        intent=IntentType.UNKNOWN,
        status="failed",
        active_agent="None",
        error="LLM API error occurred",
    )

    response = client.post(
        "/api/v1/assistant/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "book appointment"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["error"] == "LLM API error occurred"
    assert data["answer"] == "LLM API error occurred"


def test_patient_access_enforced_on_query() -> None:
    client = TestClient(app)
    # User 1 from Org 1
    reg1 = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Org 1",
            "full_name": "Doctor 1",
            "email": f"doc1-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "Cardiology",
            "project": "P1",
        },
    )
    token1 = reg1.json()["access_token"]

    # User 2 from Org 2
    reg2 = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Org 2",
            "full_name": "Doctor 2",
            "email": f"doc2-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "Cardiology",
            "project": "P1",
        },
    )
    token2 = reg2.json()["access_token"]

    # User 1 creates patient
    pat1 = client.post(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "medical_record_number": f"MRN-{uuid4().hex[:6]}",
            "given_name": "Alice",
            "family_name": "Smith",
            "department": "Cardiology",
            "project": "P1",
            "date_of_birth": "1985-05-05",
        },
    ).json()["id"]

    # User 2 attempts to query User 1's patient -> 404 (Patient not found in org)
    query_resp = client.post(
        "/api/v1/assistant/query",
        headers={"Authorization": f"Bearer {token2}"},
        json={"patient_id": pat1, "question": "Any heart issues?"},
    )
    assert query_resp.status_code == 404
