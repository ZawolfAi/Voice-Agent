import asyncio
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
reg = client.post("/api/v1/auth/register", json={"organization_name": "Test", "full_name": "Test", "email": f"test-{uuid4().hex[:6]}@example.com", "password": "Password123!", "department": "General", "project": "Default"})
headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
pat = client.post("/api/v1/patients", headers=headers, json={"medical_record_number": f"MRN-{uuid4().hex[:6]}", "given_name": "Test", "family_name": "Test", "date_of_birth": "1990-01-01"}).json()
r1 = client.post("/api/v1/assistant/chat", headers=headers, json={"message": "عايز أعمل متابعة", "patient_id": pat["id"]}).json()
print("R1:", r1)
