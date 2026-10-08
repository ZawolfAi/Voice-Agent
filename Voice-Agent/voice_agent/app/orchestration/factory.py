"""Build the configured production Orchestrator client."""

from voice_agent.app.config import Settings
from voice_agent.app.orchestration.client import MockOrchestratorClient, OrchestratorClient
from voice_agent.app.orchestration.http_client import (
    HTTPOrchestratorClient,
    OrchestratorHTTPContract,
)


class OrchestratorConfigurationError(RuntimeError):
    """Required Orchestrator connection settings are missing or invalid."""


def create_orchestrator_client(
    settings: Settings,
    *,
    contract: OrchestratorHTTPContract | None = None,
) -> OrchestratorClient:
    mode = settings.orchestrator_mode
    if mode is None:
        raise OrchestratorConfigurationError(
            "Set ORCHESTRATOR_MODE explicitly to mock, staging, or production"
        )

    if mode == "mock":
        if settings.app_env not in {"development", "test"}:
            raise OrchestratorConfigurationError(
                "Mock Orchestrator is permitted only in development or test"
            )
        return MockOrchestratorClient()

    if mode == "staging" and settings.app_env != "staging":
        raise OrchestratorConfigurationError(
            "Staging Orchestrator mode requires APP_ENV=staging"
        )
    if mode == "production" and settings.app_env != "production":
        raise OrchestratorConfigurationError(
            "Production Orchestrator mode requires APP_ENV=production"
        )
    orchestrator_url = settings.orchestrator_url or settings.careos_api_url
    if not orchestrator_url:
        raise OrchestratorConfigurationError("ORCHESTRATOR_URL is required for HTTP mode")
    if contract is None:
        from voice_agent.app.orchestration.booking_contract import CareOSContract

        contract = CareOSContract(token=settings.orchestrator_token)
    try:
        return HTTPOrchestratorClient(
            base_url=orchestrator_url,
            timeout_seconds=settings.orchestrator_timeout_seconds,
            contract=contract,
        )
    except ValueError:
        raise OrchestratorConfigurationError(
            "Orchestrator client configuration is invalid"
        ) from None