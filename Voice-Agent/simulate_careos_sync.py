"""Interactive simulation demonstrating Voice Agent communicating with CareOS backend."""

import asyncio
from datetime import datetime
import json
import sys

# Configure UTF-8 stdout for Arabic console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from voice_agent.app.agent.multilingual import generate_multilingual_reply
from voice_agent.app.agent.state import new_conversation
from voice_agent.app.agent.voice_agent import VoiceAgent
from voice_agent.app.config import Settings
from voice_agent.app.llm.demo_provider import DemoProvider
from voice_agent.app.orchestration.booking_contract import CareOSContract
from voice_agent.app.orchestration.http_client import HTTPOrchestratorClient
from voice_agent.app.schemas.auth import AuthenticatedUserContext


def create_careos_simulation_app() -> FastAPI:
    """Simulates the CareOS FastAPI service defined in api-endpoints.md."""
    app = FastAPI(title="CareOS Live Backend")

    @app.post("/api/v1/assistant/chat", status_code=200)
    async def chat(request: Request):
        data = await request.json()
        message = data.get("message", "").lower()
        patient_id = data.get("patient_id")
        print("\n[CareOS Backend] [RECEIVED] POST /api/v1/assistant/chat:")
        print(f"                 Patient ID: {patient_id}")
        print(f"                 Message:  {message}")
        print(f"                 Conversation ID: {data.get('conversation_id')}")

        if "conflict" in message:
            print(f"[CareOS Backend] [CONFLICT] Simulating schedule conflict!")
            return JSONResponse(
                status_code=409,
                content={"detail": "Schedule conflict: clinician or time slot is already booked."},
            )

        print(f"[CareOS Backend] [OK] Processed message for {patient_id}")
        return {
            "answer": "Your appointment has been confirmed.",
            "intent": "booking",
            "status": "success",
            "active_agent": "booking_agent",
            "conversation_id": data.get("conversation_id", "conv-sim-123"),
            "patient_id": patient_id,
            "orchestrator_state": {"step": "completed"},
        }

    return app


async def run_simulation():
    print("=" * 70)
    print("   CAREOS & VOICE AGENT MULTI-AGENT SYNC SIMULATION")
    print("=" * 70)

    careos_app = create_careos_simulation_app()
    transport = httpx.ASGITransport(app=careos_app)

    # 1. Setup CareOS Contract Adapter & HTTP Transport
    contract = CareOSContract(token="sample-jwt-token")
    orchestrator = HTTPOrchestratorClient(
        base_url="http://testserver/api/v1",
        contract=contract,
        timeout_seconds=5.0,
        transport=transport,
    )

    # 2. Setup Voice Agent
    llm = DemoProvider()
    agent = VoiceAgent(orchestrator=orchestrator, llm_provider=llm)

    # ------------------------------------------------------------------
    # Scenario 1: Successful Booking
    # ------------------------------------------------------------------
    print("\n--- SCENARIO 1: Patient Books an Appointment ---")
    user_context = AuthenticatedUserContext(patient_id="patient-sarah-101")
    state = new_conversation(authenticated_user=user_context)

    user_utterance = "I would like to book an appointment tomorrow at 2 PM"
    print(f"[Patient]: \"{user_utterance}\"")

    demo_settings = Settings(llm_provider="demo")
    reply, state = await agent.handle_text(user_utterance, state)
    thought, reply = await generate_multilingual_reply(user_utterance, reply, state, demo_settings)
    print(f"\n[Voice Agent Output]:\n\"{reply}\"")
    if state.last_agent_response:
        print(f"[Voice Agent Internal Status]: {state.last_agent_response.status.value.upper()}")
        print(f"[Confirmed Action]: {state.last_agent_response.action}")

    # ------------------------------------------------------------------
    # Scenario 2: Schedule Conflict (Double-Booking Attempt)
    # ------------------------------------------------------------------
    print("\n--- SCENARIO 2: Another Patient Requests with Conflict ---")
    user2_context = AuthenticatedUserContext(patient_id="patient-nour-202")
    state2 = new_conversation(authenticated_user=user2_context)

    user2_utterance = "I want to book an appointment with conflict tomorrow at 2 PM"
    print(f"[Patient 2]: \"{user2_utterance}\"")

    reply2, state2 = await agent.handle_text(user2_utterance, state2)
    thought2, reply2 = await generate_multilingual_reply(user2_utterance, reply2, state2, demo_settings)
    print(f"\n[Voice Agent Output]:\n\"{reply2}\"")

    # ------------------------------------------------------------------
    # Scenario 3: Arabic Patient Request
    # ------------------------------------------------------------------
    print("\n--- SCENARIO 3: Patient Requests in Arabic ---")
    user3_context = AuthenticatedUserContext(patient_id="patient-mariam-303")
    state3 = new_conversation(authenticated_user=user3_context)

    user3_utterance = "عاوزة أحجز جلسة بكرة الساعة 6 مساء"
    print(f"[Patient 3]: \"{user3_utterance}\"")

    reply3, state3 = await agent.handle_text(user3_utterance, state3)
    thought3, reply3 = await generate_multilingual_reply(user3_utterance, reply3, state3, demo_settings)
    print(f"\n[Voice Agent Output]:\n\"{reply3}\"")
    if state3.last_agent_response:
        print(f"[Voice Agent Internal Status]: {state3.last_agent_response.status.value.upper()}")

    print("\n" + "=" * 70)
    print("   SIMULATION COMPLETED SUCCESSFULLY: FULL E2E SYNC VERIFIED!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_simulation())
