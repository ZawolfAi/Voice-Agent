"""Compatibility bridge for running the Voice Agent backend server.

For standalone or microservice deployment, prefer `voice_agent.app.server`.
"""

from __future__ import annotations

from voice_agent.app.bootstrap import create_voice_api
from voice_agent.app.config import Settings
from voice_agent.app.server import (
    LocalDemoAuthenticator,
    build_server_app,
    main,
)

# Backward-compatible alias
build_demo_app = build_server_app

__all__ = [
    "LocalDemoAuthenticator",
    "Settings",
    "build_demo_app",
    "build_server_app",
    "create_voice_api",
    "main",
]

if __name__ == "__main__":
    main()