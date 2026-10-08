# 🎙️ Voice Agent Package Documentation

This package implements the Voice Agent core logic, multi-agent orchestrator contracts, LLM providers, and FastAPI backend service.

For complete integration instructions, system architecture, API endpoints, and configuration, please refer to the root [README.md](../../README.md) and [CareOS Integration Guide](integrations/careos/README_CAREOS_INTEGRATION.md).

## Quick Module Reference

- `app/server.py`: Standalone daemon server runner (`python -m voice_agent.app.server` on port `8765`).
- `app/bootstrap.py`: `create_voice_api` composition root for mounting into existing FastAPI hosts.
- `app/api.py`: Route handlers for turns (`/v1/voice/turns`, `/v1/voice/turns/stream`, `/v1/voice/tts`).
- `app/live_voice.py`: Real-time bidirectional WebSocket bridge (`/v1/voice/live`, `/v1/voice/transcribe`).
- `app/orchestration/booking_contract.py`: `CareOSContract` adapter for appointment scheduling and conflict handling.
- `integrations/careos/`: Pre-built CareOS platform adapters and patches.