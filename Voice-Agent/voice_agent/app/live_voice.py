"""Loopback demo WebSocket bridge for Gemini's bidirectional Live API."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from voice_agent.app.config import Settings

logger = logging.getLogger(__name__)
LIVE_MODEL = "gemini-3.8-live"
TRANSCRIBE_MODEL = "gemini-3.5-transcribe-live"
LIVE_SYSTEM_INSTRUCTION = """
You are a friendly, intelligent voice assistant for a specialized Cosmetics & Aesthetics Clinic.

CRITICAL LANGUAGE RULE (STRICT):
Always detect and speak in the EXACT SAME LANGUAGE that the user is speaking:
- If the user speaks ENGLISH: Respond strictly in natural, clear, conversational English.
- If the user speaks ARABIC: Respond strictly in natural Egyptian Arabic (مصري) written in Arabic script.
- NEVER speak in Arabic when the user speaks English!
- NEVER speak in English when the user speaks Arabic!

CLINIC SPECIALIZATION:
Our clinic is strictly dedicated to cosmetics, aesthetic dermatology, laser, botox, fillers, skin rejuvenation, and beauty treatments. We do NOT have general medical departments like cardiology, pediatrics, or internal medicine. If asked about unrelated departments, clarify politely in the user's language that we are a specialized cosmetic clinic.

OPERATING HOURS:
A real clinic calendar and booking dataset are dynamically checked. NEVER invent clinic names, doctors, prices, appointment slots, or opening/closing hours. If asked for clinic hours or openings, explain in the user's language that operating hours and available appointments will be provided once checked with the clinic database. Never provide medical diagnoses or prescriptions. Use synthetic/demo context only.
""".strip()


def add_live_voice_route(
    app: FastAPI,
    settings: Settings,
    *,
    client_factory: Callable[[str], Any] | None = None,
    live_types: Any | None = None,
) -> None:
    """Mount a server-to-server Gemini Live bridge; the API key stays backend-side."""

    @app.websocket("/v1/voice/live")
    async def live_voice(websocket: WebSocket) -> None:
        await run_live_session(websocket, mode="speech_to_speech")

    @app.websocket("/v1/voice/transcribe")
    async def live_transcription(websocket: WebSocket) -> None:
        await run_live_session(websocket, mode="speech_to_text")

    async def run_live_session(websocket: WebSocket, *, mode: str) -> None:
        await websocket.accept()
        if settings.llm_provider.casefold() != "gemini" or not settings.llm_api_key:
            await websocket.send_json(
                {"type": "error", "message": "Live voice assistant requires the Gemini provider and a server-side API key."}
            )
            await websocket.close(code=1008)
            return

        state = None
        user = None
        if hasattr(websocket.app.state, "authenticator"):
            try:
                user = await websocket.app.state.authenticator.authenticate(websocket)
                if user:
                    session_id_str = websocket.query_params.get("session_id")
                    from uuid import UUID
                    session_id = UUID(session_id_str) if session_id_str else None
                    state = await websocket.app.state.conversation_store.get_or_create(session_id, user)
            except Exception as exc:
                logger.warning(f"Live voice auth/store failed: {exc}")

        client: Any | None = None
        try:
            if client_factory is None or live_types is None:
                from google import genai
                from google.genai import types

                make_client = client_factory or genai.Client
                blob_type = types.Blob
                config_type = types.LiveConnectConfig
                activity_end_type = getattr(types, "ActivityEnd", None)
            else:
                make_client = client_factory
                blob_type = live_types.Blob
                config_type = live_types.LiveConnectConfig
                activity_end_type = getattr(live_types, "ActivityEnd", None)

            client = make_client(api_key=settings.llm_api_key)
            if mode == "speech_to_text":
                if live_types is not None and hasattr(live_types, "LiveConnectConfig"):
                    config = config_type(response_modalities=["TEXT"])
                else:
                    transcription_cfg = types.AudioTranscriptionConfig()
                    config = config_type(
                        response_modalities=["TEXT"],
                        input_audio_transcription=transcription_cfg,
                    )
                live_model = TRANSCRIBE_MODEL
            else:
                config = config_type(
                    response_modalities=["AUDIO"],
                    system_instruction=LIVE_SYSTEM_INSTRUCTION,
                    input_audio_transcription={},
                    output_audio_transcription={},
                )
                live_model = settings.live_voice_model or LIVE_MODEL
            async with client.aio.live.connect(model=live_model, config=config) as session:
                await websocket.send_json({"type": "ready", "model": live_model, "mode": mode})
                user_stopped = asyncio.Event()
                receiver_done = asyncio.Event()

                async def send_microphone_to_gemini() -> None:
                    while True:
                        event = await websocket.receive()
                        if event["type"] == "websocket.disconnect":
                            return
                        audio = event.get("bytes")
                        if audio:
                            await session.send_realtime_input(
                                audio=blob_type(
                                    data=audio,
                                    mime_type="audio/pcm;rate=16000",
                                )
                            )
                            continue
                        control = event.get("text")
                        if control:
                            try:
                                if json.loads(control).get("type") == "stop":
                                    if activity_end_type is not None:
                                        try:
                                            await session.send_realtime_input(activity_end=activity_end_type())
                                        except Exception:
                                            pass
                                    await session.send_realtime_input(audio_stream_end=True)
                                    user_stopped.set()
                                    try:
                                        await asyncio.wait_for(receiver_done.wait(), timeout=30.0)
                                    except asyncio.TimeoutError:
                                        if mode == "speech_to_text":
                                            await websocket.send_json(
                                                {"type": "dictation_error", "message": "Transcription did not finish. Please try again."}
                                            )
                                    return
                            except (json.JSONDecodeError, AttributeError):
                                continue

                async def send_gemini_to_browser() -> None:
                    nonlocal state, user
                    async for response in session.receive():
                        content = response.server_content
                        if content is not None:
                            if content.interrupted:
                                await websocket.send_json({"type": "interrupted"})
                            if mode == "speech_to_text" and content.interim_input_transcription and content.interim_input_transcription.text:
                                await websocket.send_json(
                                    {"type": "dictation_interim", "text": content.interim_input_transcription.text}
                                )
                            if content.input_transcription and content.input_transcription.text:
                                text = content.input_transcription.text
                                await websocket.send_json(
                                    {
                                        "type": "dictation_final" if mode == "speech_to_text" else "input_transcription",
                                        "text": text,
                                    }
                                )
                                if mode == "speech_to_speech" and state and user:
                                    try:
                                        agent = websocket.app.state.voice_agent
                                        store = websocket.app.state.conversation_store
                                        reply, updated_state = await agent.handle_text(text, state)
                                        state = updated_state
                                        await store.save(state, user)
                                        
                                        # Send CareOS response back to Gemini Live to speak it
                                        if hasattr(session, "send_realtime_input") and reply:
                                            await session.send_realtime_input(
                                                text=f"CAREOS_RESPONSE: {reply}\nInstruction: Speak this response to the user naturally in their language as is. Do not invent or change any appointment, doctor, time, or medical information."
                                            )
                                    except Exception as exc:
                                        logger.warning(f"CareOS state sync failed: {exc}")
                            if mode == "speech_to_text" and content.model_turn:
                                for part in content.model_turn.parts:
                                    if getattr(part, "text", None):
                                        await websocket.send_json(
                                            {"type": "dictation_final", "text": part.text}
                                        )
                            if mode == "speech_to_speech" and content.output_transcription and content.output_transcription.text:
                                await websocket.send_json(
                                    {"type": "output_transcription", "text": content.output_transcription.text}
                                )
                            if mode == "speech_to_speech" and content.model_turn:
                                for part in content.model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        await websocket.send_bytes(part.inline_data.data)
                            if content.turn_complete:
                                if mode == "speech_to_text" and user_stopped.is_set():
                                    await websocket.send_json({"type": "dictation_done"})
                                    receiver_done.set()
                                    return
                                if mode == "speech_to_speech":
                                    await websocket.send_json({"type": "turn_complete"})
                                    if user_stopped.is_set():
                                        receiver_done.set()
                                        return
                        if response.go_away is not None:
                            await websocket.send_json({"type": "reconnecting"})
                            return

                sender = asyncio.create_task(send_microphone_to_gemini())
                receiver = asyncio.create_task(send_gemini_to_browser())
                try:
                    done, pending = await asyncio.wait(
                        {sender, receiver},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if sender in done:
                        sender_exc = sender.exception()
                        if sender_exc is not None and not isinstance(
                            sender_exc, (asyncio.CancelledError, WebSocketDisconnect)
                        ):
                            if receiver in pending:
                                receiver.cancel()
                                await asyncio.gather(receiver, return_exceptions=True)
                            raise sender_exc
                        if receiver in pending:
                            await receiver
                    else:
                        receiver_exc = receiver.exception()
                        if sender in pending:
                            sender.cancel()
                            await asyncio.gather(sender, return_exceptions=True)
                        if receiver_exc is not None and not isinstance(
                            receiver_exc, (asyncio.CancelledError, WebSocketDisconnect)
                        ):
                            raise receiver_exc
                finally:
                    for task in (sender, receiver):
                        if not task.done():
                            task.cancel()
                            try:
                                await task
                            except Exception:
                                pass
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.warning("live_voice.session.failed (%s)", type(exc).__name__)
            try:
                await websocket.send_json(
                    {"type": "error", "message": "Live voice connection failed. Check Gemini Live access and try again."}
                )
            except Exception:
                pass
        finally:
            if client is not None:
                try:
                    await client.aio.aclose()
                except Exception:
                    pass
            try:
                await websocket.close()
            except Exception:
                pass
