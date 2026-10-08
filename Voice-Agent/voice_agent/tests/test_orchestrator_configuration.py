import pytest

from voice_agent.app.config import Settings
from voice_agent.app.orchestration.client import MockOrchestratorClient
from voice_agent.app.orchestration.factory import (
    OrchestratorConfigurationError,
    create_orchestrator_client,
)


def test_mock_mode_is_explicit_and_development_only() -> None:
    client = create_orchestrator_client(
        Settings(_env_file=None, app_env="DEVELOPMENT", orchestrator_mode="MOCK")
    )
    assert isinstance(client, MockOrchestratorClient)

    with pytest.raises(OrchestratorConfigurationError):
        create_orchestrator_client(
            Settings(_env_file=None, app_env="production", orchestrator_mode="mock")
        )


from voice_agent.app.orchestration.http_client import HTTPOrchestratorClient


def test_staging_mode_uses_verified_careos_contract_adapter() -> None:
    settings = Settings(
        _env_file=None,
        app_env="STAGING",
        orchestrator_mode="STAGING",
        orchestrator_url="https://placeholder.invalid",
    )
    client = create_orchestrator_client(settings)
    assert isinstance(client, HTTPOrchestratorClient)


def test_staging_mode_cannot_be_enabled_from_development() -> None:
    with pytest.raises(OrchestratorConfigurationError, match="requires APP_ENV=staging"):
        create_orchestrator_client(
            Settings(
                _env_file=None,
                app_env="development",
                orchestrator_mode="staging",
                orchestrator_url="https://placeholder.invalid",
            )
        )


def test_http_mode_requires_explicit_mode_and_url() -> None:
    with pytest.raises(OrchestratorConfigurationError, match="Set ORCHESTRATOR_MODE"):
        create_orchestrator_client(Settings(_env_file=None, orchestrator_mode=None))

    with pytest.raises(OrchestratorConfigurationError, match="ORCHESTRATOR_URL"):
        create_orchestrator_client(
            Settings(
                _env_file=None,
                app_env="staging",
                orchestrator_mode="staging",
                orchestrator_url=None,
            )
        )