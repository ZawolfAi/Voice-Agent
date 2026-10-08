import os
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_real_groq_api_integration(monkeypatch) -> None:
    api_key = os.getenv("AI_API_KEY") or get_settings().ai_api_key
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", api_key)
    monkeypatch.setenv("AI_API_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_MODEL", "openai/gpt-oss-20b")
    get_settings.cache_clear()

    try:
        client = TestClient(app)
        email = f"groq-doctor-{uuid4().hex[:6]}@example.com"
        reg_resp = client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": "Groq Real Hospital",
                "full_name": "Dr. Groq",
                "email": email,
                "password": "Password123!",
                "department": "Internal Medicine",
                "project": "GroqTest",
            },
        )
        assert reg_resp.status_code == 201
        token = reg_resp.json()["access_token"]

        # 1. Real /assistant/chat request with Groq LLM
        chat_resp = client.post(
            "/api/v1/assistant/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "عايز احجز ميعاد جلدية"},
        )
        assert chat_resp.status_code == 200
        chat_data = chat_resp.json()
        assert chat_data["intent"] == "booking"
        assert chat_data["active_agent"] == "booking"
        assert bool(chat_data["answer"])

        # 2. Real /assistant/query request with patient context
        pat_resp = client.post(
            "/api/v1/patients",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "medical_record_number": f"MRN-{uuid4().hex[:6]}",
                "given_name": "Ahmed",
                "family_name": "Hassan",
                "department": "Internal Medicine",
                "project": "GroqTest",
                "date_of_birth": "1992-03-15",
            },
        )
        assert pat_resp.status_code == 201
        patient_id = pat_resp.json()["id"]

        query_resp = client.post(
            "/api/v1/assistant/query",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "patient_id": patient_id,
                "question": "عايز أعمل متابعة للمريض بعد أسبوع",
            },
        )
        assert query_resp.status_code == 200
        query_data = query_resp.json()
        assert query_data["intent"] == "followup"
        assert query_data["active_agent"] == "followup"
        assert bool(query_data["answer"])

    finally:
        get_settings.cache_clear()
