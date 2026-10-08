"""Host-integrated HTTP API for authenticated Voice Agent conversations.

The host must provide a real authentication adapter and conversation store. This
module intentionally implements neither authentication nor an Orchestrator API
contract itself.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from voice_agent.app.agent.voice_agent import VoiceAgent
from voice_agent.app.schemas.auth import AuthenticatedUserContext
from voice_agent.app.schemas.requests import ConversationState

logger = logging.getLogger(__name__)


class HostAuthenticator(Protocol):
    async def authenticate(self, request: Request) -> AuthenticatedUserContext | None:
        """Validate host credentials and return trusted user identity, or None."""


class ConversationStore(Protocol):
    async def get_or_create(
        self,
        session_id: UUID | None,
        user: AuthenticatedUserContext,
    ) -> ConversationState:
        """Get an owned conversation or create a new one."""

    async def save(
        self,
        state: ConversationState,
        user: AuthenticatedUserContext,
    ) -> None:
        """Persist state only for its authenticated owner."""


TTSGenerator = Callable[[str], Awaitable[tuple[bytes, str] | None]]


class TextTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=20_000)
    session_id: UUID | None = None


class TurnResponse(BaseModel):
    session_id: UUID
    response_text: str
    thought: str | None = None
    intent: str | None = None
    audio_base64: str | None = None
    audio_mime_type: str | None = None


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=10_000)


class TTSResponse(BaseModel):
    audio_base64: str
    audio_mime_type: str


class InMemoryConversationStore:
    """Development/test store; use a secured persistent store in a deployed host."""

    def __init__(self) -> None:
        self._states: dict[UUID, ConversationState] = {}
        self._owners: dict[UUID, str] = {}

    async def get_or_create(
        self,
        session_id: UUID | None,
        user: AuthenticatedUserContext,
    ) -> ConversationState:
        if session_id is None:
            state = ConversationState(authenticated_user=user)
            self._states[state.session_id] = state
            self._owners[state.session_id] = user.patient_id
            return state

        state = self._states.get(session_id)
        if state is None or self._owners.get(session_id) != user.patient_id:
            raise KeyError("conversation_not_found")
        return state

    async def save(
        self,
        state: ConversationState,
        user: AuthenticatedUserContext,
    ) -> None:
        if self._owners.get(state.session_id) != user.patient_id:
            raise KeyError("conversation_not_found")
        self._states[state.session_id] = state


class UnauthenticatedHost:
    """Default-deny adapter for deployments that have not wired host auth."""

    async def authenticate(self, request: Request) -> None:
        del request
        return None


MultilingualHandler = Callable[[str, str, ConversationState], Awaitable[Any]]
MultilingualStreamer = Callable[[str, str, ConversationState], AsyncIterator[tuple[str, str]]]


def create_app(
    *,
    agent: VoiceAgent,
    authenticator: HostAuthenticator,
    conversation_store: ConversationStore,
    tts_generator: TTSGenerator | None = None,
    multilingual_handler: MultilingualHandler | None = None,
    multilingual_streamer: MultilingualStreamer | None = None,
) -> FastAPI:
    """Create the host-mounted API. Auth must be supplied by the trusted host."""
    app = FastAPI(title="Healthcare Voice Agent API", version="1.0.0")
    app.state.voice_agent = agent
    app.state.authenticator = authenticator
    app.state.conversation_store = conversation_store
    app.state.tts_generator = tts_generator
    app.state.multilingual_handler = multilingual_handler
    app.state.multilingual_streamer = multilingual_streamer

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request, exc
        return JSONResponse(status_code=422, content={"detail": "Invalid request."})

    async def resolve_identity(request: Request) -> AuthenticatedUserContext:
        try:
            user = await authenticator.authenticate(request)
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Authentication service unavailable.",
            ) from None
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required.")
        if not isinstance(user, AuthenticatedUserContext):
            raise HTTPException(status_code=503, detail="Authentication service unavailable.")
        return user

    async def resolve_state(
        session_id: UUID | None,
        user: AuthenticatedUserContext,
    ) -> ConversationState:
        try:
            return await conversation_store.get_or_create(session_id, user)
        except KeyError:
            raise HTTPException(status_code=404, detail="Conversation not found.") from None
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Conversation service unavailable.",
            ) from None

    async def make_turn_response(
        state: ConversationState,
        response_text: str,
        thought: str | None = None,
        audio_base64: str | None = None,
        audio_mime_type: str | None = None,
    ) -> TurnResponse:
        return TurnResponse(
            session_id=state.session_id,
            response_text=response_text,
            thought=thought,
            intent=state.current_intent if state.current_intent else None,
            audio_base64=audio_base64,
            audio_mime_type=audio_mime_type,
        )

    @app.get("/health", response_model=dict[str, str])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/voice/turns", response_model=TurnResponse)
    async def text_turn(payload: TextTurnRequest, request: Request) -> TurnResponse:
        user = await resolve_identity(request)
        state = await resolve_state(payload.session_id, user)
        # Guard the store boundary from accidentally returning another user's state.
        if state.patient_id != user.patient_id:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        response_text, state = await agent.handle_text(payload.text, state)
        thought = None
        if multilingual_handler is not None:
            try:
                res = await multilingual_handler(payload.text, response_text, state)
                if isinstance(res, tuple):
                    thought, response_text = res
                else:
                    response_text = str(res)
            except Exception as exc:
                logger.warning("api.multilingual_handler_failed (%s)", type(exc).__name__)

        try:
            await conversation_store.save(state, user)
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Conversation service unavailable.",
            ) from None

        audio_b64 = None
        audio_mime = None
        if tts_generator is not None:
            try:
                tts_result = await tts_generator(response_text)
                if tts_result is not None:
                    audio_bytes, audio_mime = tts_result
                    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            except Exception as exc:
                logger.warning("api.tts_generation_failed (%s)", type(exc).__name__)

        return await make_turn_response(state, response_text, thought, audio_b64, audio_mime)

    @app.post("/v1/voice/turns/stream")
    async def text_turn_stream(payload: TextTurnRequest, request: Request) -> StreamingResponse:
        user = await resolve_identity(request)
        state = await resolve_state(payload.session_id, user)
        if state.patient_id != user.patient_id:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        base_reply, state = await agent.handle_text(payload.text, state)

        async def event_generator() -> AsyncIterator[str]:
            # 1. Immediate meta event
            meta_data = {
                "session_id": str(state.session_id),
                "intent": state.current_intent if state.current_intent else None,
            }
            yield f"event: meta\ndata: {json.dumps(meta_data)}\n\n"

            accumulated_answer: list[str] = []
            accumulated_thought: list[str] = []

            # 2. Token-by-token stream (thought and answer)
            if multilingual_streamer is not None:
                try:
                    async for event_type, chunk in multilingual_streamer(payload.text, base_reply, state):
                        if event_type == "thought":
                            accumulated_thought.append(chunk)
                            yield f"event: thought\ndata: {json.dumps({'text': chunk})}\n\n"
                        else:
                            accumulated_answer.append(chunk)
                            yield f"event: answer\ndata: {json.dumps({'text': chunk})}\n\n"
                except Exception as exc:
                    logger.warning("api.stream_multilingual_failed (%s)", type(exc).__name__)
                    if not accumulated_answer:
                        accumulated_answer.append(base_reply)
                        yield f"event: answer\ndata: {json.dumps({'text': base_reply})}\n\n"
            else:
                accumulated_answer.append(base_reply)
                yield f"event: answer\ndata: {json.dumps({'text': base_reply})}\n\n"

            full_answer = "".join(accumulated_answer).strip() or base_reply

            # 3. Save state
            try:
                await conversation_store.save(state, user)
            except Exception as exc:
                logger.warning("api.stream_save_failed (%s)", type(exc).__name__)

            # 4. Synthesize speech if TTS is active
            if tts_generator is not None and full_answer:
                try:
                    tts_result = await tts_generator(full_answer)
                    if tts_result is not None:
                        audio_bytes, audio_mime = tts_result
                        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
                        audio_data = {
                            "audio_base64": audio_b64,
                            "audio_mime_type": audio_mime,
                        }
                        yield f"event: audio\ndata: {json.dumps(audio_data)}\n\n"
                except Exception as exc:
                    logger.warning("api.stream_tts_failed (%s)", type(exc).__name__)

            # 5. Done event
            yield f"event: done\ndata: {json.dumps({'status': 'ok'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/v1/voice/tts", response_model=TTSResponse)
    async def synthesize_speech(payload: TTSRequest, request: Request) -> TTSResponse:
        del request
        if tts_generator is None:
            raise HTTPException(status_code=503, detail="TTS service unavailable.")
        result = await tts_generator(payload.text)
        if result is None:
            raise HTTPException(status_code=500, detail="Could not synthesize speech.")
        audio_bytes, mime = result
        return TTSResponse(
            audio_base64=base64.b64encode(audio_bytes).decode("ascii"),
            audio_mime_type=mime,
        )

    return app