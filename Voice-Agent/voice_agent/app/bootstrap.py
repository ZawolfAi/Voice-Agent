"""Composition root used by an authenticated host to mount the Voice API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI

from voice_agent.app.agent.voice_agent import VoiceAgent
from voice_agent.app.api import ConversationStore, HostAuthenticator, create_app
from voice_agent.app.config import Settings
from voice_agent.app.llm.factory import create_llm_provider
from voice_agent.app.orchestration.factory import create_orchestrator_client
from voice_agent.app.orchestration.http_client import OrchestratorHTTPContract


def create_voice_api(
    *,
    settings: Settings,
    authenticator: HostAuthenticator,
    conversation_store: ConversationStore,
    orchestrator_contract: OrchestratorHTTPContract | None = None,
) -> FastAPI:
    """Wire Voice Agent components; host must supply identity and state storage.

    The HTTP Orchestrator mode remains unavailable unless the real service contract
    adapter is provided. This function never enables mock identity/authentication.
    """
    llm = create_llm_provider(settings)
    orchestrator = create_orchestrator_client(
        settings,
        contract=orchestrator_contract,
    )

    agent = VoiceAgent(orchestrator=orchestrator, llm_provider=llm)
    resources: list[object] = [llm, orchestrator]

    from voice_agent.app.agent.multilingual import generate_multilingual_reply, stream_multilingual_reply
    from voice_agent.app.audio.tts import generate_speech_audio
    from voice_agent.app.schemas.requests import ConversationState

    async def tts_generator(text: str) -> tuple[bytes, str] | None:
        return await generate_speech_audio(text, settings)

    async def multilingual_handler(user_text: str, base_reply: str, state: ConversationState) -> tuple[str | None, str]:
        return await generate_multilingual_reply(user_text, base_reply, state, settings)

    def multilingual_streamer(user_text: str, base_reply: str, state: ConversationState):
        return stream_multilingual_reply(user_text, base_reply, state, settings)

    app = create_app(
        agent=agent,
        authenticator=authenticator,
        conversation_store=conversation_store,
        tts_generator=tts_generator,
        multilingual_handler=multilingual_handler,
        multilingual_streamer=multilingual_streamer,
    )

    async def close_resources() -> None:
        for resource in reversed(resources):
            close: Callable[[], Awaitable[None]] | None = getattr(resource, "close", None)
            if close is not None:
                await close()

    app.router.add_event_handler("shutdown", close_resources)
    return app