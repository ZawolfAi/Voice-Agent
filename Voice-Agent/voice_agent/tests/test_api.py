import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any

import httpx

from voice_agent.app.agent.voice_agent import VoiceAgent
from voice_agent.app.api import InMemoryConversationStore, create_app
from voice_agent.app.orchestration.client import MockOrchestratorClient
from voice_agent.app.schemas.auth import AuthenticatedUserContext
from voice_agent.app.schemas.extraction import ExtractionContext, IntentExtraction
from voice_agent.app.schemas.requests import AgentRequest, Intent


class FakeLLM:
    def __init__(self, *items: IntentExtraction) -> None:
        self.items = deque(items)

    async def extract(self, text: str, context: ExtractionContext) -> IntentExtraction:
        del text, context
        return self.items.popleft()


class FakeAuthenticator:
    """Test-only stand-in for an authenticated host; no HTTP credential scheme."""

    def __init__(self, user: AuthenticatedUserContext | None) -> None:
        self.user = user

    async def authenticate(self, request: Any) -> AuthenticatedUserContext | None:
        del request
        return self.user


class FakeOrchestratorClient:
    def __init__(self):
        self.turns = 0

    async def submit(self, request: AgentRequest) -> Any:
        from voice_agent.app.schemas.responses import AgentResponse, ResponseStatus
        self.turns += 1
        if self.turns == 1:
            return AgentResponse(status=ResponseStatus.SUCCESS, action="booking", message="Sure. What day would you like to book the appointment?", conversation_id="conv-123")
        elif self.turns == 2:
            return AgentResponse(status=ResponseStatus.SUCCESS, action="booking", message="What time would you prefer?", conversation_id="conv-123")
        else:
            return AgentResponse(status=ResponseStatus.SUCCESS, action="booking", message="The clinic calendar is not connected, so I can't verify real availability. No booking was made.", conversation_id="conv-123")

    async def close(self): pass


def create_test_app(
    *,
    user: AuthenticatedUserContext | None,
    llm: FakeLLM | None = None,
) -> Any:
    provider = llm or FakeLLM(
        IntentExtraction(intent=Intent.BOOK_APPOINTMENT, specialty="cardiology"),
        IntentExtraction(intent=Intent.BOOK_APPOINTMENT, date_expression="tomorrow"),
        IntentExtraction(intent=Intent.BOOK_APPOINTMENT, preferred_time="5 PM"),
    )
    agent = VoiceAgent(
        orchestrator=FakeOrchestratorClient(),
        llm_provider=provider,
        clock=lambda: datetime(2026, 9, 30, 12, tzinfo=timezone.utc),
    )
    return create_app(
        agent=agent,
        authenticator=FakeAuthenticator(user),
        conversation_store=InMemoryConversationStore(),
    )


async def request(app: Any, method: str, url: str, **kwargs: Any) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://voice-agent.test",
    ) as client:
        return await client.request(method, url, **kwargs)


def test_health_route_is_live_without_exposing_integration_state() -> None:
    response = asyncio.run(request(create_test_app(user=None), "GET", "/health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_text_api_supports_multi_turn_authenticated_conversation() -> None:
    async def run() -> None:
        app = create_test_app(user=AuthenticatedUserContext(patient_id="trusted-patient"))
        first = await request(app, "POST", "/v1/voice/turns", json={"text": "I need a cardiologist."})
        assert first.status_code == 200
        assert first.json()["response_text"] == "Sure. What day would you like to book the appointment?"
        session_id = first.json()["session_id"]

        second = await request(
            app, "POST", "/v1/voice/turns",
            json={"text": "Tomorrow.", "session_id": session_id},
        )
        assert second.status_code == 200
        assert second.json()["response_text"] == "What time would you prefer?"

        third = await request(
            app, "POST", "/v1/voice/turns",
            json={"text": "5 PM.", "session_id": session_id},
        )
        assert third.status_code == 200
        assert "calendar is not connected" in third.json()["response_text"]
        assert "No booking was made" in third.json()["response_text"]
        assert third.json()["session_id"] == session_id

    asyncio.run(run())


def test_text_api_requires_host_authentication() -> None:
    response = asyncio.run(
        request(create_test_app(user=None), "POST", "/v1/voice/turns", json={"text": "hello"})
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_text_api_rejects_user_supplied_patient_identity() -> None:
    app = create_test_app(user=AuthenticatedUserContext(patient_id="trusted-patient"))
    response = asyncio.run(
        request(
            app, "POST", "/v1/voice/turns",
            json={"text": "hello", "patient_id": "claimed-patient"},
        )
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}


def test_session_cannot_be_used_by_another_authenticated_user() -> None:
    store = InMemoryConversationStore()

    class AuthByHeader:
        async def authenticate(self, request: Any) -> AuthenticatedUserContext | None:
            user_id = request.headers.get("x-test-user")
            return AuthenticatedUserContext(patient_id=user_id) if user_id else None

    agent = VoiceAgent(
        orchestrator=MockOrchestratorClient(),
        llm_provider=FakeLLM(IntentExtraction(intent=Intent.UNKNOWN)),
    )
    app = create_app(agent=agent, authenticator=AuthByHeader(), conversation_store=store)

    async def run() -> None:
        created = await request(
            app, "POST", "/v1/voice/turns",
            headers={"x-test-user": "patient-one"}, json={"text": "hello"},
        )
        reused = await request(
            app, "POST", "/v1/voice/turns",
            headers={"x-test-user": "patient-two"},
            json={"text": "hello", "session_id": created.json()["session_id"]},
        )
        assert created.status_code == 200
        assert reused.status_code == 404
        assert reused.json() == {"detail": "Conversation not found."}

    asyncio.run(run())


def test_text_api_includes_audio_record_when_tts_configured() -> None:
    async def fake_tts(text: str) -> tuple[bytes, str] | None:
        return b"fake-audio-record", "audio/wav"

    agent = VoiceAgent(
        orchestrator=MockOrchestratorClient(),
        llm_provider=FakeLLM(IntentExtraction(intent=Intent.UNKNOWN)),
    )
    app = create_app(
        agent=agent,
        authenticator=FakeAuthenticator(AuthenticatedUserContext(patient_id="test-patient")),
        conversation_store=InMemoryConversationStore(),
        tts_generator=fake_tts,
    )

    async def run() -> None:
        response = await request(app, "POST", "/v1/voice/turns", json={"text": "hello"})
        assert response.status_code == 200
        data = response.json()
        assert data["audio_base64"] is not None
        assert data["audio_mime_type"] == "audio/wav"

        tts_resp = await request(app, "POST", "/v1/voice/tts", json={"text": "speak this"})
        assert tts_resp.status_code == 200
        assert tts_resp.json()["audio_mime_type"] == "audio/wav"

    asyncio.run(run())


def test_text_api_streaming_endpoint_yields_sse_events() -> None:
    async def fake_streamer(user_text: str, base_reply: str, state: Any):
        del user_text, base_reply, state
        yield ("thought", "Analyzing cosmetics procedure")
        yield ("answer", "Welcome to our cosmetics clinic!")

    agent = VoiceAgent(
        orchestrator=MockOrchestratorClient(),
        llm_provider=FakeLLM(IntentExtraction(intent=Intent.GENERAL_QUESTION)),
    )
    app = create_app(
        agent=agent,
        authenticator=FakeAuthenticator(AuthenticatedUserContext(patient_id="stream-patient")),
        conversation_store=InMemoryConversationStore(),
        multilingual_streamer=fake_streamer,
    )

    async def run() -> None:
        response = await request(app, "POST", "/v1/voice/turns/stream", json={"text": "Do you do Botox?"})
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        text = response.text
        assert "event: meta" in text
        assert "event: thought" in text
        assert "Analyzing cosmetics procedure" in text
        assert "event: answer" in text
        assert "Welcome to our cosmetics clinic!" in text
        assert "event: done" in text

    asyncio.run(run())



