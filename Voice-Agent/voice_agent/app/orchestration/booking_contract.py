"""Contract adapter for CareOS backend and external booking agents."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from voice_agent.app.orchestration.http_client import (
    OrchestratorAuthenticationError,
    OrchestratorAuthorizationError,
    OrchestratorBusinessError,
    OrchestratorClientError,
    OrchestratorHTTPContract,
    OrchestratorHTTPError,
    OrchestratorUnavailableError,
    OrchestratorValidationError,
)
from voice_agent.app.schemas.requests import AgentRequest
from voice_agent.app.schemas.responses import (
    AgentResponse,
    AppointmentOption,
    ResponseStatus,
)


@dataclass
class PreparedBookingRequest:
    method: str
    path: str
    headers: dict[str, str]
    content: bytes | None


import uuid

def _normalize_patient_uuid(patient_id: str | None) -> str:
    """Ensure patient_id conforms to RFC-4122 UUID expected by CareOS backend."""
    if not patient_id:
        raise OrchestratorValidationError("A valid patient ID is required.")
    try:
        return str(uuid.UUID(str(patient_id)))
    except (ValueError, AttributeError):
        import os
        demo_id = os.getenv("DEMO_PATIENT_ID")
        if demo_id:
            try:
                return str(uuid.UUID(demo_id))
            except ValueError:
                pass
        raise OrchestratorValidationError(f"Invalid patient ID format: {patient_id}")


class CareOSContract(OrchestratorHTTPContract):
    """Adapter implementing CareOS API contract documented in api-endpoints.md and backend/app/api.py."""

    def __init__(
        self,
        *,
        token: str | None = None,
        department: str = "General",
    ) -> None:
        self.token = token
        self.department = department
        self.last_is_arabic: bool = True

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @classmethod
    async def authenticate_with_careos(
        cls,
        base_url: str = "http://127.0.0.1:8000/api/v1",
        role: str = "receptionist",
        username: str = "reception.demo",
        password: str = "Reception@123",
        timeout_seconds: float = 10.0,
    ) -> str:
        """Authenticate with CareOS demo login endpoint and obtain a valid JWT access token."""
        url = f"{base_url.rstrip('/')}/auth/demo-login"
        payload = {"role": role, "username": username, "password": password}
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("access_token", ""))

    def prepare(self, request: AgentRequest) -> PreparedBookingRequest:
        patient_uuid = _normalize_patient_uuid(request.patient_id)
        message = request.message
        
        has_arabic = bool(re.search(r"[\u0600-\u06FF]", message))
        has_latin = bool(re.search(r"[a-zA-Z]", message))
        if has_latin and not has_arabic:
            self.last_is_arabic = False
        elif has_arabic:
            self.last_is_arabic = True

        payload = {
            "message": message,
            "patient_id": patient_uuid,
            "conversation_id": request.conversation_id,
            "orchestrator_state": request.orchestrator_state,
        }

        return PreparedBookingRequest(
            method="POST",
            path="assistant/chat",
            headers=self._headers(),
            content=json.dumps(payload).encode("utf-8"),
        )

    def parse_response(self, response: httpx.Response) -> AgentResponse:
        data: Any = response.json() if response.content else {}

        if not isinstance(data, dict):
            # Fallback for unexpected format
            return AgentResponse(
                status=ResponseStatus.SUCCESS,
                action="assistant_response",
                message=str(data),
            )

        status_str = data.get("status", "success").lower()
        if status_str == "failed":
            status = ResponseStatus.ERROR
        else:
            try:
                status = ResponseStatus(status_str)
            except ValueError:
                status = ResponseStatus.SUCCESS

        answer = data.get("answer", "")
        # fallback if answer not found but error is provided
        if not answer and data.get("error"):
            answer = data.get("error")

        intent = data.get("intent", "unknown")
        conversation_id = data.get("conversation_id")
        orchestrator_state = data.get("orchestrator_state")
        active_agent = data.get("active_agent")

        return AgentResponse(
            status=status,
            action=active_agent or "assistant_response",
            message=answer,
            conversation_id=conversation_id,
            orchestrator_state=orchestrator_state,
            intent=intent,
            appointments=[],  # Not parsing individual appointments from chat directly
        )

    def map_error(self, response: httpx.Response) -> OrchestratorClientError:
        code = response.status_code
        if code == 401:
            return OrchestratorAuthenticationError("CareOS authentication failed; invalid or missing token")
        if code == 403:
            return OrchestratorAuthorizationError("CareOS permission denied for this action")
        if code == 409:
            msg = (
                "تعذر إتمام الطلب بسبب تعارض"
                if self.last_is_arabic
                else "The request could not be completed due to a conflict."
            )
            return OrchestratorBusinessError(msg)
        if code in (400, 422):
            return OrchestratorValidationError(f"Request data rejected by CareOS (HTTP {code})")
        if code == 503:
            return OrchestratorUnavailableError("CareOS service is temporarily unavailable")
        return OrchestratorHTTPError(code)


# Alias BookingAgentContract to CareOSContract for backwards compatibility
BookingAgentContract = CareOSContract
