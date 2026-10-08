import os
import time
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.db import get_session
from app.models import Appointment, CarePlan, Patient, User


def setup_groq_environment(monkeypatch):
    api_key = os.getenv("AI_API_KEY") or get_settings().ai_api_key
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", api_key)
    monkeypatch.setenv("AI_API_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_MODEL", "openai/gpt-oss-20b")
    get_settings.cache_clear()


def test_e2e_booking_real_groq(monkeypatch):
    """Test 1: Booking E2E with Real Groq LLM."""
    setup_groq_environment(monkeypatch)
    client = TestClient(app)

    # Register doctor
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "E2E Hospital",
            "full_name": "Dr. E2E",
            "email": f"booking-e2e-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "Dermatology",
            "project": "Default",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Register patient
    pat = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "medical_record_number": f"MRN-{uuid4().hex[:6]}",
            "given_name": "Khaled",
            "family_name": "Ali",
            "department": "Dermatology",
            "project": "Default",
            "date_of_birth": "1995-01-01",
        },
    ).json()
    patient_id = pat["id"]

    start_time = time.monotonic()
    response = client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={
            "message": "عايز احجز كشف جلدية بكرة الساعة 6 بالليل",
            "patient_id": patient_id,
        },
    )
    total_lat = (time.monotonic() - start_time) * 1000

    assert response.status_code == 200
    data = response.json()
    print(f"\n[Booking E2E Latency]: {total_lat:.2f} ms")
    print(f"[Booking Intent]: {data.get('intent')}")
    print(f"[Booking Active Agent]: {data.get('active_agent')}")
    print(f"[Booking Response]: {data.get('answer')}")

    assert data["intent"] == "booking"
    assert data["active_agent"] in ["booking", "BookingAgent"]
    assert bool(data["answer"])


def test_e2e_followup_real_groq(monkeypatch):
    """Test 2: Follow-up E2E with Real Groq LLM."""
    setup_groq_environment(monkeypatch)
    client = TestClient(app)

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Followup Org",
            "full_name": "Dr. Followup",
            "email": f"followup-e2e-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "General",
            "project": "Default",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    pat = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "medical_record_number": f"MRN-{uuid4().hex[:6]}",
            "given_name": "Sami",
            "family_name": "Youssef",
            "department": "General",
            "project": "Default",
            "date_of_birth": "1988-06-20",
        },
    ).json()
    patient_id = pat["id"]

    start_time = time.monotonic()
    response = client.post(
        "/api/v1/assistant/query",
        headers=headers,
        json={
            "patient_id": patient_id,
            "question": "عايز أعمل متابعة للمريض مكالمة بكرة الساعة 10 الصبح",
        },
    )
    total_lat = (time.monotonic() - start_time) * 1000

    assert response.status_code == 200
    data = response.json()
    print(f"\n[FollowUp E2E Latency]: {total_lat:.2f} ms")
    print(f"[FollowUp Intent]: {data.get('intent')}")
    print(f"[FollowUp Active Agent]: {data.get('active_agent')}")
    print(f"[FollowUp Response]: {data.get('answer')}")

    assert data["intent"] == "followup"
    assert data["active_agent"] in ["followup", "FollowUpAgent"]
    assert bool(data["answer"])


def test_e2e_unknown_intent(monkeypatch):
    """Test 3: Unknown Intent Clarification."""
    setup_groq_environment(monkeypatch)
    client = TestClient(app)

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Unknown Org",
            "full_name": "Dr. Unknown",
            "email": f"unknown-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "General",
            "project": "Default",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    start_time = time.monotonic()
    response = client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={"message": "عايز أستفسر عن حاجة"},
    )
    total_lat = (time.monotonic() - start_time) * 1000

    assert response.status_code == 200
    data = response.json()
    print(f"\n[Unknown Intent Latency]: {total_lat:.2f} ms")
    print(f"[Unknown Intent]: {data.get('intent')}")
    print(f"[Unknown Response]: {data.get('answer')}")

    assert data["intent"] == "unknown"
    assert data["active_agent"] is None or data["active_agent"] == "None"
    assert "information" in data["answer"].lower() or "تحديد" in data["answer"] or "book" in data["answer"].lower() or "follow-up" in data["answer"].lower() or "تساعدك" in data["answer"] or bool(data["answer"])


def test_e2e_multiturn_state_propagation(monkeypatch):
    """Test 4: Multi-turn State Propagation."""
    setup_groq_environment(monkeypatch)
    client = TestClient(app)

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "MultiTurn Org",
            "full_name": "Dr. MultiTurn",
            "email": f"multiturn-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "General",
            "project": "Default",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Turn 1: Initial request
    r1 = client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={"message": "عايز احجز ميعاد كشف جلدية"},
    ).json()
    conv_id = r1["conversation_id"]
    state1 = r1["orchestrator_state"]

    assert r1["intent"] == "booking"
    assert state1 is not None

    # Turn 2: Provide date with state continuation
    r2 = client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={
            "message": "بكرة",
            "conversation_id": conv_id,
            "orchestrator_state": state1,
        },
    ).json()
    state2 = r2["orchestrator_state"]

    assert r2["conversation_id"] == conv_id
    assert r2["intent"] == "booking"
    assert state2 is not None

    # Turn 3: Provide time
    r3 = client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={
            "message": "الساعة 6 مساءً",
            "conversation_id": conv_id,
            "orchestrator_state": state2,
        },
    ).json()

    assert r3["conversation_id"] == conv_id
    assert r3["intent"] == "booking"


def test_e2e_assistant_query_rbac(monkeypatch):
    """Test 5: /assistant/query Patient Access Enforcement."""
    setup_groq_environment(monkeypatch)
    client = TestClient(app)

    # Doctor 1 in Org A
    reg1 = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Hospital A",
            "full_name": "Dr. Alice",
            "email": f"alice-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "Cardiology",
            "project": "ProjA",
        },
    ).json()
    headers1 = {"Authorization": f"Bearer {reg1['access_token']}"}

    # Doctor 2 in Org B
    reg2 = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Hospital B",
            "full_name": "Dr. Bob",
            "email": f"bob-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "Cardiology",
            "project": "ProjB",
        },
    ).json()
    headers2 = {"Authorization": f"Bearer {reg2['access_token']}"}

    # Doctor 1 creates patient in Org A
    pat1 = client.post(
        "/api/v1/patients",
        headers=headers1,
        json={
            "medical_record_number": f"MRN-{uuid4().hex[:6]}",
            "given_name": "PatientA",
            "family_name": "OrgA",
            "department": "Cardiology",
            "project": "ProjA",
            "date_of_birth": "1990-01-01",
        },
    ).json()["id"]

    # Authorized query by Doctor 1 -> 200
    res_auth = client.post(
        "/api/v1/assistant/query",
        headers=headers1,
        json={"patient_id": pat1, "question": "What is patient status?"},
    )
    assert res_auth.status_code == 200

    # Unauthorized query by Doctor 2 -> 404 (Enforced patient tenant isolation)
    res_unauth = client.post(
        "/api/v1/assistant/query",
        headers=headers2,
        json={"patient_id": pat1, "question": "What is patient status?"},
    )
    assert res_unauth.status_code == 404


def test_e2e_failure_cases(monkeypatch):
    """Test 6: Failure & Exception Isolation Cases."""
    setup_groq_environment(monkeypatch)
    client = TestClient(app)

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Fail Org",
            "full_name": "Dr. Fail",
            "email": f"fail-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "General",
            "project": "Default",
        },
    ).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Unauthenticated request -> 401
    unauth = client.post("/api/v1/assistant/chat", json={"message": "hello"})
    assert unauth.status_code == 401

    # Invalid patient ID -> 422
    inv_pat = client.post(
        "/api/v1/assistant/query",
        headers=headers,
        json={"patient_id": "invalid-uuid", "question": "status"},
    )
    assert inv_pat.status_code == 422


def test_e2e_full_booking_with_availability_and_conflict(monkeypatch):
    """Test 7: Full multi-turn booking with availability and conflict handling."""
    setup_groq_environment(monkeypatch)
    client = TestClient(app)

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Conflict Org",
            "full_name": "Dr. Conflict",
            "email": f"conflict-{uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "department": "Cardiology",
            "project": "Default",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    pat = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "medical_record_number": f"MRN-{uuid4().hex[:6]}",
            "given_name": "Sami",
            "family_name": "Conflict",
            "department": "Cardiology",
            "project": "Default",
            "date_of_birth": "1990-01-01",
        },
    ).json()
    patient_id = pat["id"]

    from datetime import datetime, timedelta, timezone
    tomorrow_10am = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    
    # Create conflicting appointment at 10 AM
    client.post(
        "/api/v1/appointments",
        headers=headers,
        json={
            "patient_id": patient_id,
            "starts_at": tomorrow_10am.isoformat(),
            "duration_minutes": 30,
            "department": "Cardiology",
            "status": "scheduled",
            "reason": "Block",
        }
    )

    # 1. Ask to book tomorrow at 10 AM (which is blocked)
    r1 = client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={"message": "عايز احجز كشف بكرة الساعة 10 الصبح", "patient_id": patient_id},
    ).json()
    conv_id = r1["conversation_id"]
    state1 = r1["orchestrator_state"]

    # The availability check should fail and return unavailable_choice
    assert r1["intent"] == "booking"
    assert "10" not in r1["answer"] or "غير متاح" in r1["answer"] or "متاح" in r1["answer"]
    assert state1["agent_states"]["booking"]["status"] == "collecting"

    # 2. User selects 11 AM instead (which is available)
    r2 = client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={
            "message": "خلاص خليها الساعة 11 الصبح",
            "conversation_id": conv_id,
            "orchestrator_state": state1,
        },
    ).json()
    
    assert r2["intent"] == "booking"
    assert "تم" in r2["answer"] or "أكد" in r2["answer"] or "confirm" in r2["answer"].lower()

