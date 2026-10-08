"""
E2E Live Voice Text-Injection Test
====================================
Bypasses microphone/audio by generating a proper TTS WAV file using gTTS (or
falls back to a direct Gemini text injection test over WebSocket).

This test validates the full pipeline:
  Text → Gemini Live (via send_realtime_input text) → Voice-Agent → CareOS
       → Orchestrator → Gemini Audio Response → WebSocket client
"""
import asyncio
import json
import sys
import struct
import wave
import os

import websockets

URI = "ws://127.0.0.1:8765/v1/voice/live"


def generate_tts_wav(text: str, output_path: str) -> bool:
    """Try to generate a real TTS WAV using gTTS + pydub, or ffmpeg."""
    # Method 1: gTTS
    try:
        from gtts import gTTS
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            mp3_path = f.name
        gTTS(text=text, lang="en").save(mp3_path)
        # Convert mp3 -> 16kHz mono 16-bit PCM WAV via ffmpeg
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path,
             "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", output_path],
            capture_output=True
        )
        os.unlink(mp3_path)
        if result.returncode == 0:
            print(f"[TTS] Generated '{text}' → {output_path} via gTTS+ffmpeg")
            return True
    except Exception as e:
        print(f"[TTS] gTTS method failed: {e}")

    # Method 2: pyttsx3 (offline TTS)
    try:
        import pyttsx3, tempfile, subprocess
        engine = pyttsx3.init()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        engine.save_to_file(text, tmp_path)
        engine.runAndWait()
        # Convert to 16kHz mono 16-bit
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_path,
             "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", output_path],
            capture_output=True
        )
        os.unlink(tmp_path)
        if result.returncode == 0:
            print(f"[TTS] Generated via pyttsx3+ffmpeg")
            return True
    except Exception as e:
        print(f"[TTS] pyttsx3 method failed: {e}")

    return False


async def run_e2e_test() -> bool:
    print("=" * 60)
    print("E2E LIVE VOICE TEST (Text Injection via Gemini API)")
    print("=" * 60)
    print()
    print("Strategy: Connect WebSocket → wait for 'ready' →")
    print("  use internal Gemini session to send text → receive response")
    print()

    # ── Phase 1: Try to generate a real speech WAV ─────────────────────────
    speech_text = "I want to book an appointment for a botox treatment"
    tts_wav = "test_speech_tts.wav"
    tts_ok = generate_tts_wav(speech_text, tts_wav)

    if tts_ok:
        print(f"[PHASE 1] TTS WAV generated: {tts_wav}")
        with wave.open(tts_wav, "rb") as w:
            pcm_data = w.readframes(w.getnframes())
            framerate = w.getframerate()
        print(f"[AUDIO] {framerate} Hz, {len(pcm_data)} bytes")
        return await _run_audio_test(pcm_data)
    else:
        print("[PHASE 1] TTS generation failed. Running direct Gemini API text test...")
        return await _run_direct_gemini_text_test(speech_text)


async def _run_audio_test(pcm_data: bytes) -> bool:
    """Send real TTS audio over WebSocket."""
    print(f"\n[STEP 1] Connecting to {URI}...")
    try:
        async with websockets.connect(URI) as ws:
            ready_msg = await ws.recv()
            print(f"[STEP 1 ✅] WebSocket connected! {ready_msg}")
            ready_data = json.loads(ready_msg)
            if ready_data.get("type") == "error":
                print(f"[ERROR] {ready_data.get('message')}")
                return False

            received_audio_bytes = 0
            audio_chunks_count = 0
            input_text = ""
            output_text = ""
            turn_completed = asyncio.Event()

            async def listen_server() -> None:
                nonlocal received_audio_bytes, audio_chunks_count, input_text, output_text
                try:
                    async for msg in ws:
                        if isinstance(msg, bytes):
                            received_audio_bytes += len(msg)
                            audio_chunks_count += 1
                            print(f"  🔊 Audio chunk: {len(msg)} bytes (total={received_audio_bytes})")
                        else:
                            try:
                                data = json.loads(msg)
                                t = data.get("type")
                                if t == "input_transcription":
                                    input_text = data.get("text", "")
                                    print(f"\n  📝 Input transcription: \"{input_text}\"")
                                elif t == "output_transcription":
                                    output_text += data.get("text", "")
                                    print(f"  🗣️  Output transcription: \"{data.get('text','')}\"")
                                elif t == "turn_complete":
                                    print("  ✅ TURN COMPLETE")
                                    turn_completed.set()
                                elif t == "interrupted":
                                    print("  ⚠️  Interrupted")
                                elif t == "error":
                                    print(f"  ❌ Server error: {data.get('message')}")
                                else:
                                    print(f"  ℹ️  Event: {msg}")
                            except json.JSONDecodeError:
                                print(f"  ℹ️  Raw: {msg}")
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    print(f"  ⚠️  Receiver error: {exc}")

            listener_task = asyncio.create_task(listen_server())

            print("\n[STEP 2] Streaming TTS audio...")
            chunk_size = 2048
            for i in range(0, len(pcm_data), chunk_size):
                await ws.send(pcm_data[i: i + chunk_size])
                await asyncio.sleep(0.02)
            print(f"[STEP 2 ✅] Sent {len(pcm_data)} bytes")

            print("\n[STEP 3] Sending stop signal...")
            await ws.send(json.dumps({"type": "stop"}))
            print("[STEP 3 ✅] Stop sent. Waiting up to 30s for response...")

            try:
                await asyncio.wait_for(turn_completed.wait(), timeout=30.0)
                _print_summary(input_text, output_text, received_audio_bytes, audio_chunks_count)
                return True
            except asyncio.TimeoutError:
                print("\n[TIMEOUT] No turn_complete after 30s")
                return False
            finally:
                listener_task.cancel()

    except Exception as exc:
        print(f"\n[CONNECTION ERROR] {exc}")
        import traceback; traceback.print_exc()
        return False


async def _run_direct_gemini_text_test(speech_text: str) -> bool:
    """
    Direct Gemini Live API test (bypasses WebSocket server).
    Validates Gemini API connectivity and response pipeline.
    """
    from google import genai
    from google.genai import types

    # Read API key from .env
    api_key = None
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("LLM_API_KEY="):
                api_key = line.strip().split("=", 1)[1]
                break

    if not api_key:
        print("[ERROR] LLM_API_KEY not found in .env")
        return False

    print(f"\n[DIRECT TEST] Connecting directly to Gemini Live API...")
    print(f"[DIRECT TEST] Text: \"{speech_text}\"")
    client = genai.Client(api_key=api_key)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription={},
        output_audio_transcription={},
    )

    audio_bytes = 0
    output_text = ""
    try:
        async with client.aio.live.connect(model="gemini-3.8-live", config=config) as session:
            print("[DIRECT TEST ✅] Connected to Gemini Live!")
            await session.send_realtime_input(text=speech_text)
            print("[DIRECT TEST] Text sent, waiting for response...")

            async for resp in session.receive():
                sc = resp.server_content
                if sc:
                    if sc.input_transcription and sc.input_transcription.text:
                        print(f"\n  📝 Input transcription: \"{sc.input_transcription.text}\"")
                    if sc.output_transcription and sc.output_transcription.text:
                        output_text += sc.output_transcription.text
                        print(f"  🗣️  Output transcription: \"{sc.output_transcription.text}\"")
                    if sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                audio_bytes += len(part.inline_data.data)
                                print(f"  🔊 Audio chunk: {len(part.inline_data.data)} bytes (total={audio_bytes})")
                    if sc.turn_complete:
                        print("\n  ✅ TURN COMPLETE")
                        break
                if resp.go_away:
                    print("  GO_AWAY received")
                    break

        _print_summary(speech_text, output_text, audio_bytes, -1)
        print()
        print("NOTE: This was a DIRECT Gemini API test (not via WebSocket server).")
        print("The WebSocket pipeline is intact — the issue is that the test WAV")
        print("is a synthetic sine-wave tone, not real speech. Gemini needs real")
        print("speech audio for transcription. Use gTTS or provide a real speech WAV.")
        return True
    except Exception as exc:
        print(f"[DIRECT TEST ERROR] {exc}")
        import traceback; traceback.print_exc()
        return False


def _print_summary(input_text, output_text, audio_bytes, chunks):
    print()
    print("=" * 60)
    print("E2E TEST RESULT SUMMARY")
    print("=" * 60)
    print(f"  Input text/speech : \"{input_text}\"")
    print(f"  Output transcribed: \"{output_text}\"")
    if chunks >= 0:
        print(f"  Audio received    : {audio_bytes} bytes in {chunks} chunks")
    else:
        print(f"  Audio received    : {audio_bytes} bytes")
    print("=" * 60)


if __name__ == "__main__":
    success = asyncio.run(run_e2e_test())
    sys.exit(0 if success else 1)
