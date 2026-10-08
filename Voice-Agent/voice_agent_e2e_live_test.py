import asyncio
import json
import os
import sys
import wave
import websockets

URI = "ws://127.0.0.1:8765/v1/voice/live"
WAV_PATH = sys.argv[1] if len(sys.argv) > 1 else "test_input_16k.wav"


async def run_e2e_test() -> bool:
    print("=" * 60)
    print("STARTING E2E LIVE VOICE TEST")
    print(f"Target WebSocket: {URI}")
    print(f"Audio File     : {os.path.abspath(WAV_PATH)}")
    print("=" * 60)

    # ── Validate file exists ──────────────────────────────────────────────────
    if not os.path.exists(WAV_PATH):
        print(f"[FILE ERROR] File not found: {os.path.abspath(WAV_PATH)}")
        return False

    try:
        with wave.open(WAV_PATH, "rb") as w:
            n_channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            framerate = w.getframerate()
            n_frames = w.getnframes()
            duration_s = n_frames / framerate if framerate else 0
            pcm_data = w.readframes(n_frames)
        print(
            f"[AUDIO] File     : {os.path.basename(WAV_PATH)}"
        )
        print(
            f"[AUDIO] Format   : {framerate} Hz, {n_channels} ch, {sampwidth*8}-bit PCM"
        )
        print(
            f"[AUDIO] Size     : {len(pcm_data)} bytes, duration ~{duration_s:.2f}s"
        )
        if n_channels != 1 or sampwidth != 2 or framerate != 16000:
            print(f"[AUDIO WARNING] Expected mono/16kHz/16-bit. Got: {n_channels}ch/{framerate}Hz/{sampwidth*8}bit")
            print("[AUDIO WARNING] Gemini may not transcribe audio that doesn't match PCM 16kHz mono 16-bit.")
    except Exception as exc:
        print(f"[AUDIO ERROR] Failed to read WAV file: {exc}")
        return False

    print(f"\n[STEP 1] Connecting to {URI}...")
    try:
        async with websockets.connect(URI) as ws:
            ready_msg = await ws.recv()
            print(f"[STEP 1 SUCCESS] WebSocket connected! Ready message: {ready_msg}")
            ready_data = json.loads(ready_msg)
            if ready_data.get("type") == "error":
                print(f"[ERROR] Server returned error: {ready_data.get('message')}")
                return False

            received_audio_bytes = 0
            audio_chunks_count = 0
            input_text = ""
            output_text = ""
            turn_completed = asyncio.Event()

            last_event: dict = {}

            async def listen_server() -> None:
                nonlocal received_audio_bytes, audio_chunks_count, input_text, output_text, last_event
                try:
                    async for msg in ws:
                        if isinstance(msg, bytes):
                            received_audio_bytes += len(msg)
                            audio_chunks_count += 1
                            last_event = {"type": "audio_chunk", "bytes": len(msg)}
                            print(
                                f"  🔊 [Gemini Audio Chunk] {len(msg)} bytes (total={received_audio_bytes} in {audio_chunks_count} chunks)"
                            )
                        else:
                            try:
                                data = json.loads(msg)
                                last_event = data
                                event_type = data.get("type")
                                if event_type == "input_transcription":
                                    input_text = data.get("text", "")
                                    print(f"\n  📝 [INPUT TRANSCRIPTION]: \"{input_text}\"")
                                    print(
                                        "  ⚡ [Voice-Agent → CareOS]: Forwarding to CareOS /assistant/chat..."
                                    )
                                elif event_type == "output_transcription":
                                    output_text = data.get("text", "")
                                    print(f"  🗣️  [OUTPUT TRANSCRIPTION]: \"{output_text}\"")
                                elif event_type == "turn_complete":
                                    print("  ✅ [TURN COMPLETE]: Gemini Live finished output turn.")
                                    turn_completed.set()
                                elif event_type == "interrupted":
                                    print("  ⚠️  [INTERRUPTED]: Gemini Live output interrupted.")
                                elif event_type == "error":
                                    print(f"  ❌ [SERVER ERROR]: {data.get('message')}")
                                elif event_type == "ready":
                                    pass  # already printed
                                else:
                                    print(f"  ℹ️  [Server Event]: {msg}")
                            except json.JSONDecodeError:
                                last_event = {"type": "raw", "text": msg}
                                print(f"  ℹ️  [Raw Text]: {msg}")
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    print(f"  ⚠️  [Receiver Exception]: {exc}")

            listener_task = asyncio.create_task(listen_server())

            print("\n[STEP 2] Streaming PCM audio chunks to WebSocket...")
            chunk_size = 2048
            chunks_sent = 0
            bytes_sent = 0

            for i in range(0, len(pcm_data), chunk_size):
                chunk = pcm_data[i : i + chunk_size]
                await ws.send(chunk)
                chunks_sent += 1
                bytes_sent += len(chunk)
                await asyncio.sleep(0.02)

            print(f"[STEP 2 SUCCESS] Sent {bytes_sent} PCM audio bytes in {chunks_sent} chunks.")

            print("\n[STEP 3] Sending stop control signal...")
            await ws.send(json.dumps({"type": "stop"}))
            print("[STEP 3 SUCCESS] Stop signal sent. Awaiting Gemini Live & CareOS response...")

            try:
                await asyncio.wait_for(turn_completed.wait(), timeout=25.0)
                print("\n" + "=" * 60)
                print("E2E LIVE VOICE TEST COMPLETED SUCCESSFULLY!")
                print(f"User Speech Transcribed: \"{input_text}\"")
                print(f"CareOS → Gemini Output Transcribed: \"{output_text}\"")
                print(
                    f"Total Gemini Audio Received: {received_audio_bytes} bytes ({audio_chunks_count} chunks)"
                )
                print("=" * 60)
                return True
            except asyncio.TimeoutError:
                print("\n[TIMEOUT] Timed out waiting for turn completion after 25s.")
                print(f"[TIMEOUT] Last server event received: {json.dumps(last_event, ensure_ascii=False)}")
                if not input_text:
                    print("[TIMEOUT] No INPUT TRANSCRIPTION received — Gemini did not detect speech in audio.")
                    print("[TIMEOUT] Verify that the WAV contains real speech (not silence/tone).")
                elif not output_text and received_audio_bytes == 0:
                    print("[TIMEOUT] INPUT TRANSCRIPTION received but no CareOS/Gemini response yet.")
                return False
            finally:
                listener_task.cancel()

    except Exception as exc:
        print(f"\n[CONNECTION ERROR] E2E test failed: {exc}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_e2e_test())
    sys.exit(0 if success else 1)
