"""Interactive text-only demonstration; no real patient or appointment system."""

import asyncio
import logging

from voice_agent.app.agent.state import new_conversation
from voice_agent.app.agent.voice_agent import VoiceAgent
from voice_agent.app.config import settings
from voice_agent.app.llm.factory import create_llm_provider
from voice_agent.app.llm.provider import LLMConfigurationError
from voice_agent.app.orchestration.factory import (
    OrchestratorConfigurationError,
    create_orchestrator_client,
)


async def run_cli() -> None:
    logging.basicConfig(level=settings.log_level.upper())
    try:
        llm_provider = create_llm_provider(settings)
    except LLMConfigurationError as exc:
        print(f"LLM configuration error: {exc}")
        return
    try:
        orchestrator = create_orchestrator_client(settings)
    except OrchestratorConfigurationError as exc:
        print(f"Orchestrator configuration error: {exc}")
        close = getattr(llm_provider, "close", None)
        if close is not None:
            await close()
        return

    agent = VoiceAgent(orchestrator=orchestrator, llm_provider=llm_provider)
    try:
        state = new_conversation()
        print(
            f"Development text CLI ({settings.orchestrator_mode.upper()} Orchestrator). "
            "No identity verification is configured; account actions require "
            "patient context from a trusted authenticated host. Type 'exit' to quit."
        )
        while True:
            user_text = input("Patient: ").strip()
            if user_text.casefold() in {"exit", "quit"}:
                break
            reply, state = await agent.handle_text(user_text, state)
            print(f"Voice Agent: {reply}")
    finally:
        await orchestrator.close()
        close = getattr(llm_provider, "close", None)
        if close is not None:
            await close()


if __name__ == "__main__":
    asyncio.run(run_cli())