import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

from app.main import app

def setup_groq_environment(monkeypatch):
    import os
    if not os.getenv("GROQ_API_KEY"):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_dummy")

@pytest.fixture
def client(monkeypatch):
    setup_groq_environment(monkeypatch)
    return TestClient(app)

@pytest.fixture
def auth_headers(client):
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "E2E Followup Org",
            "full_name": "Dr. Followup",
            "email": f"dr.followup-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "General",
            "project": "E2E",
        },
    )
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def patient_id(client, auth_headers):
    pat = client.post(
        "/api/v1/patients",
        headers=auth_headers,
        json={
            "medical_record_number": f"MRN-{uuid4().hex[:6]}",
            "given_name": "Test",
            "family_name": "Followup",
            "date_of_birth": "1990-01-01",
        },
    ).json()
    return pat["id"]


def test_followup_basic_flow_and_multiturn_missing_info(client, auth_headers, patient_id):
    r1 = client.post(
        "/api/v1/assistant/chat",
        headers=auth_headers,
        json={"message": "عايز أعمل متابعة", "patient_id": patient_id},
    ).json()
    assert r1["intent"] == "followup"
    assert r1["active_agent"] == "followup"
    state1 = r1["orchestrator_state"]
    assert state1["followup_state"]["status"] == "collecting"
    
    conv_id = r1["conversation_id"]

    r2 = client.post(
        "/api/v1/assistant/chat",
        headers=auth_headers,
        json={"message": "لمراجعة التحاليل بكرة الساعة 10 الصبح", "patient_id": patient_id, "conversation_id": conv_id, "orchestrator_state": state1},
    ).json()
    assert r2["conversation_id"] == conv_id
    assert r2["patient_id"] == patient_id
    state2 = r2["orchestrator_state"]
    assert state2["followup_state"]["status"] == "confirming"
    
    r3 = client.post(
        "/api/v1/assistant/chat",
        headers=auth_headers,
        json={"message": "تمام", "patient_id": patient_id, "conversation_id": conv_id, "orchestrator_state": state2},
    ).json()
    state3 = r3["orchestrator_state"]
    assert state3["followup_state"]["status"] == "completed"


def test_existing_followup_update_and_confirmation_safety(client, auth_headers, patient_id):
    # First create it via chat
    r_create1 = client.post("/api/v1/assistant/chat", headers=auth_headers, json={"message": "عايز أعمل متابعة", "patient_id": patient_id}).json()
    r_create2 = client.post("/api/v1/assistant/chat", headers=auth_headers, json={"message": "مكالمة بكرة الساعة 10 الصبح", "patient_id": patient_id, "conversation_id": r_create1["conversation_id"], "orchestrator_state": r_create1["orchestrator_state"]}).json()
    r_create3 = client.post("/api/v1/assistant/chat", headers=auth_headers, json={"message": "تمام", "patient_id": patient_id, "conversation_id": r_create2["conversation_id"], "orchestrator_state": r_create2["orchestrator_state"]}).json()
    
    f_id = r_create3["orchestrator_state"]["followup_state"]["result"]["id"]

    r1 = client.post(
        "/api/v1/assistant/chat",
        headers=auth_headers,
        json={"message": "عايز أغير ميعاد المتابعة لبكرة الساعة 12", "patient_id": patient_id},
    ).json()
    assert r1["intent"] == "followup"
    state1 = r1["orchestrator_state"]
    assert state1["followup_state"]["action"] == "modify"
    assert state1["followup_state"]["followup_id"] == f_id
    assert state1["followup_state"]["status"] == "confirming"

    r2 = client.post(
        "/api/v1/assistant/chat",
        headers=auth_headers,
        json={"message": "ممكن", "patient_id": patient_id, "conversation_id": r1["conversation_id"], "orchestrator_state": state1},
    ).json()
    state2 = r2["orchestrator_state"]
    assert state2["followup_state"]["status"] == "confirming" 

    r3 = client.post(
        "/api/v1/assistant/chat",
        headers=auth_headers,
        json={"message": "لا خلاص", "patient_id": patient_id, "conversation_id": r2["conversation_id"], "orchestrator_state": state2},
    ).json()
    state3 = r3["orchestrator_state"]
    assert state3["followup_state"]["status"] == "new"


def test_orchestrator_routing(client, auth_headers, patient_id):
    r_book = client.post("/api/v1/assistant/chat", headers=auth_headers, json={"message": "عايز احجز جلدية", "patient_id": patient_id}).json()
    assert r_book["intent"] == "booking"
    
    r_follow = client.post("/api/v1/assistant/chat", headers=auth_headers, json={"message": "عايز أعمل متابعة", "patient_id": patient_id}).json()
    assert r_follow["intent"] == "followup"
    
    r_unk = client.post("/api/v1/assistant/chat", headers=auth_headers, json={"message": "عايز أطلب بيتزا", "patient_id": patient_id}).json()
    assert r_unk["intent"] == "unknown"


def test_cross_agent_isolation(client, auth_headers, patient_id):
    r1 = client.post("/api/v1/assistant/chat", headers=auth_headers, json={"message": "عايز احجز كشف", "patient_id": patient_id}).json()
    state1 = r1["orchestrator_state"]
    assert state1["active_agent"] == "booking"
    
    r2 = client.post("/api/v1/assistant/chat", headers=auth_headers, json={"message": "طب عايز أعمل متابعة", "patient_id": patient_id, "conversation_id": r1["conversation_id"], "orchestrator_state": state1}).json()
    state2 = r2["orchestrator_state"]
    assert state2["active_agent"] == "followup"
    
    r3 = client.post("/api/v1/assistant/chat", headers=auth_headers, json={"message": "نرجع للحجز، دكتور جلدية", "patient_id": patient_id, "conversation_id": r2["conversation_id"], "orchestrator_state": state2}).json()
    state3 = r3["orchestrator_state"]
    assert state3["active_agent"] == "booking"
    assert state3["booking_state"]["specialty"] == "dermatology"
    assert state3["followup_state"]["status"] == "collecting"
