"""Standalone API server daemon for Voice Agent & Multi-Agent Reception System."""

from __future__ import annotations

import logging
import os
from typing import Any

import uvicorn
from fastapi import FastAPI, Request

from voice_agent.app.api import ConversationStore, HostAuthenticator, InMemoryConversationStore
from voice_agent.app.bootstrap import create_voice_api
from voice_agent.app.config import Settings
from voice_agent.app.live_voice import LIVE_MODEL, add_live_voice_route
from voice_agent.app.schemas.auth import AuthenticatedUserContext


class LocalDemoAuthenticator:
    """Default identity provider for development/standalone daemon mode."""

    async def authenticate(self, request: Request) -> AuthenticatedUserContext:
        del request
        demo_id = os.getenv("DEMO_PATIENT_ID")
        if not demo_id:
            raise RuntimeError("DEMO_PATIENT_ID environment variable is required for local standalone daemon mode")
        return AuthenticatedUserContext(patient_id=demo_id)


def build_server_app(settings: Settings | None = None) -> FastAPI:
    """Build the standalone Voice Agent service application."""
    configured = settings or Settings()
    if configured.app_env != "development":
        raise RuntimeError("The standalone server is allowed only in APP_ENV=development")

    if configured.orchestrator_mode is None:
        configured = configured.model_copy(update={"orchestrator_mode": "mock"})
    elif configured.orchestrator_mode not in ("mock", "staging"):
        raise RuntimeError("Set ORCHESTRATOR_MODE=mock or staging to use the standalone server")

    authenticator: HostAuthenticator = LocalDemoAuthenticator()
    store: ConversationStore = InMemoryConversationStore()

    from voice_agent.app.orchestration.booking_contract import BookingAgentContract

    api_settings = configured
    if configured.orchestrator_mode == "staging":
        api_settings = configured.model_copy(update={"app_env": "staging"})

    app = create_voice_api(
        settings=api_settings,
        authenticator=authenticator,
        conversation_store=store,
        orchestrator_contract=BookingAgentContract(token=configured.orchestrator_token),
    )

    # Attach WebSocket live bidirectional voice & transcription routes
    add_live_voice_route(app, configured)

    @app.get("/", include_in_schema=False)
    async def service_index() -> dict[str, Any]:
        """Root service status and documentation entrypoint."""
        return {
            "name": "Voice Agent & Multi-Agent API",
            "status": "online",
            "version": "1.0.0",
            "environment": configured.app_env,
            "docs_url": "/docs",
            "endpoints": {
                "turns": "POST /v1/voice/turns",
                "turns_stream": "POST /v1/voice/turns/stream",
                "tts": "POST /v1/voice/tts",
                "live_voice": "WS /v1/voice/live",
                "transcribe": "WS /v1/voice/transcribe",
                "health": "GET /health",
                "status": "GET /status",
            },
        }

    @app.get("/status", include_in_schema=False)
    @app.get("/demo/status", include_in_schema=False)
    async def service_status() -> dict[str, bool | str]:
        """Non-sensitive runtime model and provider configuration status."""
        live_enabled = (
            configured.llm_provider.casefold() == "gemini"
            and bool(configured.llm_api_key)
        )
        return {
            "liveVoiceEnabled": live_enabled,
            "liveVoiceModel": configured.live_voice_model or LIVE_MODEL,
            "llmProvider": configured.llm_provider.casefold(),
            "llmModel": configured.llm_model or (
                "gemini-3.5-flash-lite" if configured.llm_provider.casefold() == "gemini"
                else "gpt-4o-mini" if configured.llm_provider.casefold() == "openai"
                else "offline demo"
            ),
        }

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        app = build_server_app()
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from None

    host = os.getenv("VOICE_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("VOICE_AGENT_PORT", "8765"))
    print(f"Voice Agent Backend Daemon listening on http://{host}:{port}")
    print(f"API Docs available at http://{host}:{port}/docs")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        ws="websockets-sansio",
    )


if __name__ == "__main__":
    main()
