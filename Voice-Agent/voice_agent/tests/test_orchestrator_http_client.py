"""Transport tests use a deliberately test-only API contract and MockTransport."""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
import pytest

from voice_agent.app.agent.state import new_conversation
from voice_agent.app.agent.voice_agent import VoiceAgent
from voice_agent.app.orchestration.http_client import (
    HTTPOrchestratorClient,
    OrchestratorClientError,
    OrchestratorHTTPError,
    OrchestratorResponseError,
    OrchestratorTimeoutError,
    OrchestratorUnavailableError,
    PreparedOrchestratorRequest,
)
from voice_agent.app.schemas.auth import AuthenticatedUserContext
from voice_agent.app.schemas.requests import AgentRequest
from voice_agent.app.schemas.responses import (
    AgentResponse,
    AppointmentOption,
    ResponseStatus,
)


@dataclass
class PreparedRequestFixture:
    method: str
    path: str
    headers: dict[str, str]
    content: bytes | None


class OnlyOrchestratorContractFixture:
    """A fabricated, local wire contract for transport tests only, not production."""

    def prepare(self, request: AgentRequest) -> PreparedRequestFixture:
        # This fixture intentionally chooses POST/path/headers only for test assertions.
        return PreparedRequestFixture(
            method="POST",
            path="/test-contract/submit",
            headers={"content-type": "application/json"},
            content=request.model_dump_json().encode(),
        )

    def parse_response(self, response: httpx.Response) -> AgentResponse:
        return AgentResponse.model_validate(response.json())

    def map_error(self, response: httpx.Response) -> OrchestratorClientError:
        # Test fixture intentionally does not guess API-specific status semantics.
        return OrchestratorHTTPError(response.status_code)


def make_request() -> AgentRequest:
    return AgentRequest(
        request_id=uuid4(),
        session_id=uuid4(),
        message="I want to book an appointment",
        patient_id="test-patient",
    )


def client_for(handler: Any, *, timeout_seconds: float = 0.05) -> HTTPOrchestratorClient:
    return HTTPOrchestratorClient(
        base_url="https://orchestrator.test/base",
        contract=OnlyOrchestratorContractFixture(),
        timeout_seconds=timeout_seconds,
        transport=httpx.MockTransport(handler),
    )


def test_successful_request_uses_only_test_adapter_wire_details() -> None:
    async def run() -> None:
        captured: dict[str, Any] = {}
        expected = AgentResponse(
            status=ResponseStatus.SUCCESS,
            action="appointment_options",
            appointments=[AppointmentOption(doctor="Test Fixture Provider", time="09:00")],
        )

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["headers"] = request.headers
            captured["body"] = request.read()
            return httpx.Response(200, json=expected.model_dump(mode="json"))

        client = client_for(handler)
        request = make_request()
        try:
            response = await client.submit(request)
        finally:
            await client.close()

        payload = json.loads(captured["body"])
        assert captured["url"] == "https://orchestrator.test/base/test-contract/submit"
        assert captured["method"] == "POST"  # Test contract only, not claimed service API.
        assert payload["request_id"] == str(request.request_id)
        assert payload["message"] == "I want to book an appointment"
        assert response == expected

    asyncio.run(run())


def test_invalid_response_is_rejected() -> None:
    async def run() -> None:
        client = client_for(
            lambda request: httpx.Response(
                200,
                json={"status": "success", "action": "options", "unexpected": "bad"},
            )
        )
        try:
            with pytest.raises(OrchestratorResponseError):
                await client.submit(make_request())
        finally:
            await client.close()

    asyncio.run(run())


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 409, 422, 500, 502, 503, 504])
def test_http_errors_are_sanitized_and_not_retried(status_code: int, caplog: Any) -> None:
    async def run() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(status_code, text="private-patient-payload-token")

        client = client_for(handler)
        try:
            with pytest.raises(OrchestratorHTTPError) as caught:
                await client.submit(make_request())
        finally:
            await client.close()
        assert caught.value.status_code == status_code
        assert calls == 1
        assert "private-patient-payload-token" not in caplog.text

    asyncio.run(run())


def test_timeout_is_classified_and_not_retried() -> None:
    async def run() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("private details", request=request)

        client = client_for(handler)
        try:
            with pytest.raises(OrchestratorTimeoutError):
                await client.submit(make_request())
        finally:
            await client.close()
        assert calls == 1

    asyncio.run(run())


def test_connection_failure_is_classified_and_not_retried() -> None:
    async def run() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ConnectError("private details", request=request)

        client = client_for(handler)
        try:
            with pytest.raises(OrchestratorUnavailableError):
                await client.submit(make_request())
        finally:
            await client.close()
        assert calls == 1

    asyncio.run(run())


def test_no_options_result_is_rendered_without_fabrication() -> None:
    async def run() -> None:
        body = AgentResponse(
            status=ResponseStatus.SUCCESS,
            action="appointment_options",
            appointments=[],
        ).model_dump(mode="json")
        client = client_for(lambda request: httpx.Response(200, json=body))

        class FakeLLM:
            pass

        agent = VoiceAgent(
            orchestrator=client,
            llm_provider=FakeLLM(),
            clock=lambda: datetime(2026, 9, 28, 12, tzinfo=timezone.utc),
        )
        try:
            reply, state = await agent.handle_text(
                "Book a cardiologist tomorrow at 5 PM.",
                new_conversation(AuthenticatedUserContext(patient_id="test-patient")),
            )
        finally:
            await client.close()
        assert reply == "The healthcare platform returned no appointment options."
        assert state.last_agent_response is not None
        assert state.last_agent_response.appointments == []

    asyncio.run(run())


def test_booking_failure_response_is_not_reported_as_completed() -> None:
    async def run() -> None:
        body = AgentResponse(
            status=ResponseStatus.ERROR,
            action="booking_failed",
            message="The Orchestrator could not complete the booking.",
        ).model_dump(mode="json")
        client = client_for(lambda request: httpx.Response(200, json=body))

        class FakeLLM:
            pass

        agent = VoiceAgent(
            orchestrator=client,
            llm_provider=FakeLLM(),
            clock=lambda: datetime(2026, 9, 28, 12, tzinfo=timezone.utc),
        )
        try:
            reply, _ = await agent.handle_text(
                "Book a cardiologist tomorrow at 5 PM.",
                new_conversation(AuthenticatedUserContext(patient_id="test-patient")),
            )
        finally:
            await client.close()
        assert reply == "The Orchestrator could not complete the booking."
        assert "booked" not in reply.casefold()

    asyncio.run(run())