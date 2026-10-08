"""Contract-neutral HTTP transport for a verified Orchestrator integration.

This module deliberately does not choose an HTTP method, endpoint, wire schema,
auth scheme, correlation header, HTTP status mapping, or retry policy. Those are
owned by a contract adapter derived from the actual Orchestrator specification.
"""

from __future__ import annotations

import logging
from typing import Protocol
from time import perf_counter

import httpx
from pydantic import ValidationError

from voice_agent.app.schemas.requests import AgentRequest
from voice_agent.app.schemas.responses import AgentResponse

logger = logging.getLogger(__name__)


class OrchestratorClientError(RuntimeError):
    """Base class for sanitized client errors."""


class OrchestratorAuthenticationError(OrchestratorClientError):
    """Use only when the verified service contract identifies auth failures."""


class OrchestratorAuthorizationError(OrchestratorClientError):
    """Use only when the verified service contract identifies permission failures."""


class OrchestratorValidationError(OrchestratorClientError):
    """Use only when the verified service contract identifies input validation errors."""


class OrchestratorUnavailableError(OrchestratorClientError):
    """The service could not be reached or reported unavailable."""


class OrchestratorTimeoutError(OrchestratorClientError):
    """The configured request deadline elapsed."""


class OrchestratorResponseError(OrchestratorClientError):
    """Response content was malformed or could not be validated."""


class OrchestratorBusinessError(OrchestratorClientError):
    """The Orchestrator reported a business-level failure."""


class OrchestratorHTTPError(OrchestratorClientError):
    """An HTTP error not mapped by a verified contract adapter."""

    def __init__(self, status_code: int) -> None:
        super().__init__("orchestrator_http_error")
        self.status_code = status_code


class PreparedOrchestratorRequest(Protocol):
    """Wire request prepared from actual service documentation by an adapter."""

    method: str
    path: str
    headers: dict[str, str]
    content: bytes | None


class OrchestratorHTTPContract(Protocol):
    """Contract-specific serialization, auth, and response/error validation."""

    def prepare(self, request: AgentRequest) -> PreparedOrchestratorRequest:
        """Return the verified method/path/headers/body for this request."""

    def parse_response(self, response: httpx.Response) -> AgentResponse:
        """Validate and map a successful service response to AgentResponse."""

    def map_error(self, response: httpx.Response) -> OrchestratorClientError:
        """Map an error response using verified service semantics only."""


class HTTPOrchestratorClient:
    """Reusable HTTP transport. A verified contract adapter is mandatory."""

    def __init__(
        self,
        base_url: str,
        *,
        contract: OrchestratorHTTPContract,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("Orchestrator base URL is required")
        if timeout_seconds <= 0:
            raise ValueError("Orchestrator timeout must be positive")
        if contract is None:
            raise ValueError("A verified Orchestrator contract adapter is required")

        self._contract = contract
        self._client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )

    async def submit(self, request: AgentRequest) -> AgentResponse:
        """Send once through the supplied contract and validate its response."""
        started = perf_counter()
        request_id = str(request.request_id)
        intent = "unknown"
        try:
            prepared = self._contract.prepare(request)
            response = await self._client.request(
                method=prepared.method,
                url=prepared.path,
                headers=prepared.headers,
                content=prepared.content,
            )
        except httpx.TimeoutException:
            self._log_failure(request_id, intent, "timeout", started)
            raise OrchestratorTimeoutError("orchestrator_request_timed_out") from None
        except httpx.RequestError as exc:
            self._log_failure(request_id, intent, "unavailable", started,
                              error_type=type(exc).__name__)
            raise OrchestratorUnavailableError("orchestrator_unavailable") from None
        except OrchestratorClientError:
            self._log_failure(request_id, intent, "contract_error", started)
            raise
        except Exception as exc:
            # Avoid leaking request data or exceptions from the contract adapter.
            self._log_failure(request_id, intent, "contract_error", started,
                              error_type=type(exc).__name__)
            raise OrchestratorResponseError("orchestrator_contract_adapter_failed") from None

        if not response.is_success:
            try:
                error = self._contract.map_error(response)
                if not isinstance(error, OrchestratorClientError):
                    raise TypeError("contract error mapper returned an invalid error")
            except Exception as exc:
                self._log_failure(request_id, intent, "http_error", started,
                                  http_status=response.status_code,
                                  error_type=type(exc).__name__)
                raise OrchestratorHTTPError(response.status_code) from None
            self._log_failure(request_id, intent, "http_error", started,
                              http_status=response.status_code,
                              error_category=type(error).__name__)
            raise error

        try:
            result = self._contract.parse_response(response)
            result = AgentResponse.model_validate(result)
        except (ValidationError, TypeError, ValueError):
            self._log_failure(request_id, intent, "invalid_response", started,
                              http_status=response.status_code)
            raise OrchestratorResponseError("orchestrator_response_invalid") from None
        except Exception as exc:
            self._log_failure(request_id, intent, "invalid_response", started,
                              http_status=response.status_code,
                              error_type=type(exc).__name__)
            raise OrchestratorResponseError("orchestrator_response_invalid") from None

        logger.info(
            "orchestrator.http.completed",
            extra=self._log_context(
                request_id, intent, result.status.value, started,
                http_status=response.status_code,
            ),
        )
        return result

    @staticmethod
    def _log_context(
        request_id: str,
        intent: str,
        outcome: str,
        started: float,
        **extra: object,
    ) -> dict[str, object]:
        return {
            "request_id": request_id,
            "intent": intent,
            "outcome": outcome,
            "latency_ms": round((perf_counter() - started) * 1000),
            **extra,
        }

    @classmethod
    def _log_failure(
        cls,
        request_id: str,
        intent: str,
        outcome: str,
        started: float,
        **extra: object,
    ) -> None:
        logger.warning(
            "orchestrator.http.failed",
            extra=cls._log_context(request_id, intent, outcome, started, **extra),
        )

    async def close(self) -> None:
        await self._client.aclose()