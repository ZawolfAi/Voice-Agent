import asyncio
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from voice_agent.app.config import Settings
from voice_agent.app.demo_server import LocalDemoAuthenticator, build_demo_app
from voice_agent.app.llm.demo_provider import DemoProvider
from voice_agent.app.llm.factory import create_llm_provider
from voice_agent.app.llm.provider import LLMConfigurationError
from voice_agent.app.schemas.extraction import ExtractionContext
from voice_agent.app.schemas.requests import Intent
from voice_agent.app.server import build_server_app


def test_offline_demo_provider_recognizes_sample_booking_phrases() -> None:
    async def run() -> None:
        provider = DemoProvider()
        context = ExtractionContext(current_date="2026-10-03")

        english = await provider.extract("I need a cardiologist.", context)
        arabic = await provider.extract(
            "محتاج أحجز مع دكتور قلب بكرة الساعة ٥ مساءً.", context
        )

        assert english.intent == Intent.BOOK_APPOINTMENT
        assert english.specialty == "cardiology"
        assert arabic.intent == Intent.BOOK_APPOINTMENT
        assert arabic.specialty == "cardiology"
        assert arabic.date_expression == "tomorrow"
        assert arabic.preferred_time == "5 PM"

    asyncio.run(run())


def test_demo_provider_is_rejected_outside_development_and_test() -> None:
    with pytest.raises(LLMConfigurationError, match="development/test only"):
        create_llm_provider(
            Settings(_env_file=None, app_env="production", llm_provider="demo")
        )


def test_server_refuses_non_development_settings(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "voice_agent.app.server.create_voice_api",
        lambda **kwargs: pytest.fail("must reject before creating the API"),
    )
    monkeypatch.setattr(
        "voice_agent.app.demo_server.create_voice_api",
        lambda **kwargs: pytest.fail("must reject before creating the API"),
    )
    with pytest.raises(RuntimeError, match="APP_ENV=development"):
        build_demo_app(
            Settings(
                _env_file=None,
                app_env="production",
                orchestrator_mode="mock",
                llm_provider="demo",
            )
        )


def test_server_serves_status_and_api_metadata(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "voice_agent.app.server.create_voice_api",
        lambda **kwargs: FastAPI(),
    )
    monkeypatch.setattr(
        "voice_agent.app.demo_server.create_voice_api",
        lambda **kwargs: FastAPI(),
    )
    app = build_server_app(
        Settings(
            _env_file=None,
            app_env="development",
            orchestrator_mode="mock",
            llm_provider="demo",
        )
    )

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            page = await client.get("/")
            status = await client.get("/demo/status")
        assert page.status_code == 200
        assert "Voice Agent" in page.text
        assert "type=\"file\"" not in page.text
        assert "audio-turns" not in page.text
        paths = {route.path for route in app.routes}
        assert "/v1/voice/live" in paths
        assert "/v1/voice/audio-turns" not in paths
        assert status.json() == {
            "liveVoiceEnabled": False,
            "liveVoiceModel": "gemini-3.8-live",
            "llmProvider": "demo",
            "llmModel": "offline demo",
        }

    asyncio.run(run())


def test_local_demo_authenticator_uses_only_fixed_test_identity(monkeypatch: Any) -> None:
    class DummyRequest:
        pass

    monkeypatch.setenv("DEMO_PATIENT_ID", "local-service-user")
    user = asyncio.run(LocalDemoAuthenticator().authenticate(DummyRequest()))  # type: ignore[arg-type]
    assert user.patient_id == "local-service-user"