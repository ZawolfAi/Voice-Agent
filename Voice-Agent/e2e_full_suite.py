import asyncio
import json
import os
import sys
import wave
import time
import websockets

URI = os.getenv("VOICE_AGENT_WS_URI", "ws://127.0.0.1:8765/v1/voice/live")
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "test_audio")

async def send_audio_file(ws, filepath: str):
    with wave.open(filepath, "rb") as w:
        pcm = w.readframes(w.getnframes())

    chunk_size = 2048
    for i in range(0, len(pcm), chunk_size):
        await ws.send(pcm[i : i + chunk_size])
        await asyncio.sleep(0.02)

    await ws.send(json.dumps({"type": "stop"}))

async def run_single_turn(audio_filename: str, session_id: str | None = None) -> dict:
    url = f"{URI}?session_id={session_id}" if session_id else URI
    audio_path = os.path.join(AUDIO_DIR, audio_filename)

    t0 = time.perf_counter()
    async with websockets.connect(url) as ws:
        t_conn = time.perf_counter()
        ready_msg = await ws.recv()
        t_ready = time.perf_counter()

        await send_audio_file(ws, audio_path)
        t_send_end = time.perf_counter()

        input_text = ""
        output_text = ""
        audio_bytes = 0
        turn_complete = False
        t_input_tx = None
        t_output_tx = None
        t_turn_complete = None

        async for msg in ws:
            if isinstance(msg, bytes):
                audio_bytes += len(msg)
            else:
                data = json.loads(msg)
                event_type = data.get("type")
                if event_type == "input_transcription":
                    t_input_tx = time.perf_counter()
                    input_text = data.get("text", "")
                elif event_type == "output_transcription":
                    if not t_output_tx:
                        t_output_tx = time.perf_counter()
                    output_text += data.get("text", "")
                elif event_type == "turn_complete":
                    t_turn_complete = time.perf_counter()
                    turn_complete = True
                    break
                elif event_type == "error":
                    raise RuntimeError(f"Server error: {data.get('message')}")

    lat_total = t_turn_complete - t0 if t_turn_complete else 0
    lat_input = t_input_tx - t_send_end if t_input_tx else 0
    lat_output = t_output_tx - t_input_tx if (t_output_tx and t_input_tx) else 0

    return {
        "audio_file": audio_filename,
        "input_transcription": input_text,
        "output_transcription": output_text,
        "audio_bytes": audio_bytes,
        "turn_complete": turn_complete,
        "latency_total": lat_total,
        "latency_input": lat_input,
        "latency_output": lat_output,
        "ws_connect_time": t_conn - t0,
        "gemini_ready_time": t_ready - t_conn,
    }

async def test_booking_basic():
    print("\n[TEST] Booking — basic request")
    res = await run_single_turn("booking_01_request.wav")
    print(f"  Input : \"{res['input_transcription']}\"")
    print(f"  Output: \"{res['output_transcription']}\"")
    print(f"  Stats : Audio={res['audio_bytes']}b, Total Latency={res['latency_total']:.2f}s")
    assert res["input_transcription"] and res["output_transcription"] and res["turn_complete"]
    return True

async def test_booking_multiturn():
    print("\n[TEST] Booking — multi-turn")
    import uuid
    sid = str(uuid.uuid4())
    r1 = await run_single_turn("booking_01_request.wav", sid)
    r2 = await run_single_turn("booking_02_evening.wav", sid)
    print(f"  Turn 1 Output: \"{r1['output_transcription']}\"")
    print(f"  Turn 2 Output: \"{r2['output_transcription']}\"")
    assert r1["turn_complete"] and r2["turn_complete"]
    return True

async def test_booking_confirmation():
    print("\n[TEST] Booking — confirmation")
    import uuid
    sid = str(uuid.uuid4())
    r1 = await run_single_turn("booking_01_request.wav", sid)
    r2 = await run_single_turn("booking_02_evening.wav", sid)
    r3 = await run_single_turn("booking_03_confirm.wav", sid)
    print(f"  Confirmation Output: \"{r3['output_transcription']}\"")
    assert r3["turn_complete"]
    return True

async def test_booking_bargein():
    print("\n[TEST] Booking — barge-in")
    async with websockets.connect(URI) as ws:
        await ws.recv()
        await send_audio_file(ws, os.path.join(AUDIO_DIR, "booking_01_request.wav"))
        chunks = 0
        barged = False
        async for msg in ws:
            if isinstance(msg, bytes):
                chunks += 1
                if chunks == 2 and not barged:
                    # Send second audio file during output
                    second_audio = os.path.join(AUDIO_DIR, "booking_02_evening.wav")
                    with wave.open(second_audio, "rb") as w:
                        pcm = w.readframes(w.getnframes())
                    await ws.send(pcm[:4096])
                    await ws.send(json.dumps({"type": "stop"}))
                    barged = True
            else:
                data = json.loads(msg)
                if data.get("type") == "turn_complete":
                    break
        assert barged
    return True

async def test_followup_basic():
    print("\n[TEST] Follow-up — basic request")
    res = await run_single_turn("followup_01_request.wav")
    print(f"  Input : \"{res['input_transcription']}\"")
    print(f"  Output: \"{res['output_transcription']}\"")
    print(f"  Stats : Audio={res['audio_bytes']}b, Total Latency={res['latency_total']:.2f}s")
    assert res["input_transcription"] and res["output_transcription"] and res["turn_complete"]
    return True

async def test_followup_multiturn():
    print("\n[TEST] Follow-up — multi-turn")
    import uuid
    sid = str(uuid.uuid4())
    r1 = await run_single_turn("followup_01_request.wav", sid)
    r2 = await run_single_turn("followup_02_status.wav", sid)
    print(f"  Turn 1 Output: \"{r1['output_transcription']}\"")
    print(f"  Turn 2 Output: \"{r2['output_transcription']}\"")
    assert r1["turn_complete"] and r2["turn_complete"]
    return True

async def test_followup_bargein():
    print("\n[TEST] Follow-up — barge-in")
    async with websockets.connect(URI) as ws:
        await ws.recv()
        await send_audio_file(ws, os.path.join(AUDIO_DIR, "followup_01_request.wav"))
        chunks = 0
        barged = False
        async for msg in ws:
            if isinstance(msg, bytes):
                chunks += 1
                if chunks == 2 and not barged:
                    second_audio = os.path.join(AUDIO_DIR, "followup_02_status.wav")
                    with wave.open(second_audio, "rb") as w:
                        pcm = w.readframes(w.getnframes())
                    await ws.send(pcm[:4096])
                    await ws.send(json.dumps({"type": "stop"}))
                    barged = True
            else:
                data = json.loads(msg)
                if data.get("type") == "turn_complete":
                    break
        assert barged
    return True

async def test_disconnect_reconnect():
    print("\n[TEST] Disconnect / reconnect")
    async with websockets.connect(URI) as ws:
        await ws.recv()
        await ws.send(b"\x00" * 2048)
        await ws.close()
    await asyncio.sleep(0.3)
    async with websockets.connect(URI) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "stop"}))
    return True

async def main():
    print("============================================================")
    print("CAREOS VOICE AGENT COMPREHENSIVE E2E SUITE")
    print("============================================================")

    tests = [
        ("Booking — basic request", test_booking_basic),
        ("Booking — multi-turn", test_booking_multiturn),
        ("Booking — confirmation", test_booking_confirmation),
        ("Booking — barge-in", test_booking_bargein),
        ("Follow-up — basic request", test_followup_basic),
        ("Follow-up — multi-turn", test_followup_multiturn),
        ("Follow-up — barge-in", test_followup_bargein),
        ("Disconnect / reconnect", test_disconnect_reconnect),
    ]

    results = []
    for name, func in tests:
        try:
            ok = await func()
            results.append((name, True, None))
        except Exception as exc:
            print(f"  ❌ FAILED: {exc}")
            import traceback
            traceback.print_exc()
            results.append((name, False, str(exc)))

    print("\n" + "=" * 60)
    print("E2E SUITE SUMMARY REPORT")
    print("=" * 60)
    all_ok = True
    for name, ok, err in results:
        status = "[PASS]" if ok else "[FAIL]"
        print(f"{status:8s} {name:30s}")
        if not ok:
            all_ok = False
            print(f"         Error: {err}")
    print("=" * 60)
    return all_ok

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
