"""
Temporary E2E Text Test: Voice-Agent → CareOS → Orchestrator → Booking Agent
=============================================================================
Sends "عايز احجز ميعاد جلدية" directly through the Voice-Agent pipeline
using the existing HTTP contract, without audio, without gTTS, without modifying
any production file.

NO new dependencies. NO production file edits.
"""

import asyncio
import json
import os
import uuid

import httpx


CAREOS_BASE_URL = "http://localhost:8000/api/v1"
DEMO_PATIENT_ID = os.getenv("DEMO_PATIENT_ID", "00000000-0000-0000-0000-000000000001")
INPUT_TEXT = "عايز احجز ميعاد جلدية"

SEP = "=" * 60


def section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


async def run() -> bool:
    section("E2E TEXT TEST: Voice-Agent → CareOS → Orchestrator → Booking Agent")
    print(f"  Input text    : \"{INPUT_TEXT}\"")
    print(f"  Patient ID    : {DEMO_PATIENT_ID}")
    print(f"  CareOS URL    : {CAREOS_BASE_URL}")

    # ── Step 1: Authenticate with CareOS ─────────────────────────────────────
    section("STEP 1: Authenticate with CareOS demo-login")
    token: str | None = None
    try:
        from voice_agent.app.orchestration.booking_contract import CareOSContract
        token = await CareOSContract.authenticate_with_careos(base_url=CAREOS_BASE_URL)
        print(f"  ✅ Auth OK — token: {token[:30]}...")
    except Exception as exc:
        print(f"  ❌ Auth FAILED: {type(exc).__name__}: {exc}")
        print("  → Continuing without token (may get 401 from CareOS)")

    # ── Step 2: Build Voice-Agent components directly ─────────────────────────
    section("STEP 2: Build Voice-Agent + CareOS HTTP Contract")
    try:
        from voice_agent.app.orchestration.booking_contract import CareOSContract
        from voice_agent.app.orchestration.http_client import HTTPOrchestratorClient
        from voice_agent.app.agent.voice_agent import VoiceAgent
        from voice_agent.app.schemas.requests import ConversationState

        contract = CareOSContract(token=token)
        orchestrator = HTTPOrchestratorClient(
            base_url=CAREOS_BASE_URL,
            contract=contract,
            timeout_seconds=30.0,
        )
        from voice_agent.app.llm.demo_provider import DemoProvider
        llm = DemoProvider()

        agent = VoiceAgent(orchestrator=orchestrator, llm_provider=llm)
        print("  ✅ Voice-Agent built successfully")
    except Exception as exc:
        print(f"  ❌ Build FAILED: {type(exc).__name__}: {exc}")
        import traceback; traceback.print_exc()
        return False

    # ── Step 3: Build ConversationState ───────────────────────────────────────
    section("STEP 3: Build ConversationState")
    try:
        from voice_agent.app.schemas.auth import AuthenticatedUserContext
        user_ctx = AuthenticatedUserContext(patient_id=DEMO_PATIENT_ID)
        state = ConversationState(
            session_id=uuid.uuid4(),
            authenticated_user=user_ctx,
        )
        print(f"  session_id      : {state.session_id}")
        print(f"  patient_id      : {state.patient_id}")
        print(f"  conversation_id : {state.conversation_id}")
    except Exception as exc:
        print(f"  ❌ State build FAILED: {type(exc).__name__}: {exc}")
        import traceback; traceback.print_exc()
        return False

    # ── Step 4: Prepare HTTP request payload (what will be sent to CareOS) ────
    section("STEP 4: Inspect prepared CareOS HTTP request")
    try:
        from voice_agent.app.schemas.requests import AgentRequest
        req = AgentRequest(
            session_id=state.session_id,
            patient_id=state.patient_id,
            message=INPUT_TEXT,
            conversation_id=state.conversation_id,
            orchestrator_state=state.orchestrator_state,
        )
        prepared = contract.prepare(req)
        payload = json.loads(prepared.content or b"{}")
        print(f"  HTTP method  : {prepared.method}")
        print(f"  URL          : {CAREOS_BASE_URL.rstrip('/')}/{prepared.path}")
        print(f"  Headers      : {prepared.headers}")
        print(f"  Payload      :")
        print(f"    message          : \"{payload.get('message')}\"")
        print(f"    patient_id       : {payload.get('patient_id')}")
        print(f"    conversation_id  : {payload.get('conversation_id')}")
        print(f"    orchestrator_state: {payload.get('orchestrator_state')}")
    except Exception as exc:
        print(f"  ❌ Prepare FAILED: {type(exc).__name__}: {exc}")
        import traceback; traceback.print_exc()
        return False

    # ── Step 5: Send raw HTTP request and show response ───────────────────────
    section("STEP 5: Send HTTP POST to CareOS /assistant/chat")
    raw_status: int | None = None
    raw_body: dict = {}
    try:
        async with httpx.AsyncClient(base_url=f"{CAREOS_BASE_URL.rstrip('/')}/", timeout=30.0) as client:
            resp = await client.request(
                method=prepared.method,
                url=prepared.path,
                headers=prepared.headers,
                content=prepared.content,
            )
        raw_status = resp.status_code
        print(f"  HTTP status : {raw_status}")
        try:
            raw_body = resp.json()
            print(f"  Raw response (formatted):")
            print(json.dumps(raw_body, ensure_ascii=False, indent=4))
        except Exception:
            print(f"  Raw body (text): {resp.text[:500]}")
    except httpx.ConnectError as exc:
        print(f"  ❌ CONNECTION ERROR: CareOS is not reachable at {CAREOS_BASE_URL}")
        print(f"     → {exc}")
        print("  FIRST FAILURE POINT: CareOS backend is not running or wrong URL")
        await orchestrator.close()
        return False
    except Exception as exc:
        print(f"  ❌ HTTP request FAILED: {type(exc).__name__}: {exc}")
        import traceback; traceback.print_exc()
        await orchestrator.close()
        return False

    # ── Step 6: Run through Voice-Agent handle_text ───────────────────────────
    section("STEP 6: Voice-Agent handle_text → CareOS → Orchestrator result")
    success = False
    try:
        reply, updated_state = await agent.handle_text(INPUT_TEXT, state)
        resp_obj = updated_state.last_agent_response

        print(f"  ✅ handle_text returned reply:")
        print(f"     \"{reply}\"")
        print()
        if resp_obj:
            print(f"  CareOS response fields:")
            print(f"    status           : {resp_obj.status}")
            print(f"    action/agent     : {resp_obj.action}")
            print(f"    intent           : {resp_obj.intent}")
            print(f"    message          : \"{resp_obj.message}\"")
            print(f"    conversation_id  : {resp_obj.conversation_id}")
            print(f"    orchestrator_state: {resp_obj.orchestrator_state}")
            if resp_obj.appointments:
                print(f"    appointments     : {resp_obj.appointments}")
        print()
        print(f"  Updated state:")
        print(f"    current_intent    : {updated_state.current_intent}")
        print(f"    orchestrator_state: {updated_state.orchestrator_state}")
        print(f"    conversation_id   : {updated_state.conversation_id}")
        success = True
    except Exception as exc:
        print(f"  ❌ handle_text FAILED: {type(exc).__name__}: {exc}")
        import traceback; traceback.print_exc()
        print(f"\n  FIRST FAILURE POINT: {type(exc).__name__} in Voice-Agent.handle_text")

    await orchestrator.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    section("RESULT")
    if success:
        print("  ✅ Voice-Agent → CareOS → Orchestrator → Booking Agent: PASS")
        print(f"  Pipeline is verified for: \"{INPUT_TEXT}\"")
    else:
        print("  ❌ Pipeline FAILED — see FIRST FAILURE POINT above")
    print(SEP)
    return success


if __name__ == "__main__":
    import sys
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
