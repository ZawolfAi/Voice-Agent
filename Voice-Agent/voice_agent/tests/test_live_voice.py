import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from starlette.testclient import TestClient

from voice_agent.app.config import Settings
from voice_agent.app.live_voice import LIVE_MODEL, LIVE_SYSTEM_INSTRUCTION, add_live_voice_route


class FakeBlob:
    def __init__(self, *, data: bytes, mime_type: str) -> None:
        self.data = data
        self.mime_type = mime_type


class FakeLiveConnectConfig:
    def __init__(self, **kwargs: Any) -> None:
        self.values = kwargs


class FakeLiveSession:
    def __init__(self) -> None:
        self.received_audio: list[FakeBlob] = []
        self.input_done = asyncio.Event()

    async def send_realtime_input(
        self, *, audio: FakeBlob | None = None, audio_stream_end: bool = False
    ) -> None:
        if audio is not None:
            self.received_audio.append(audio)
            self.input_done.set()
        if audio_stream_end:
            self.input_done.set()

    async def receive(self):
        await self.input_done.wait()
        yield SimpleNamespace(
            server_content=SimpleNamespace(
                interrupted=False,
                input_transcription=SimpleNamespace(text="محتاج أحجز مع دكتور قلب"),
                output_transcription=SimpleNamespace(text="أهلاً، أقدر أساعدك إزاي؟"),
                model_turn=SimpleNamespace(
                    parts=[SimpleNamespace(inline_data=SimpleNamespace(data=b"pcm-audio"))]
                ),
                turn_complete=True,
            ),
            go_away=None,
        )


class FakeLiveClient:
    def __init__(self, session: FakeLiveSession) -> None:
        self.session = session
        self.config: FakeLiveConnectConfig | None = None
        self.model: str | None = None
        self.closed = False
        self.aio = SimpleNamespace(aclose=self.aclose)
        self.aio.live = SimpleNamespace(connect=self.connect)

    @asynccontextmanager
    async def connect(self, *, model: str, config: FakeLiveConnectConfig):
        self.model = model
        self.config = config
        yield self.session

    async def aclose(self) -> None:
        self.closed = True


def test_live_route_requires_gemini_configuration() -> None:
    app = FastAPI()
    add_live_voice_route(
        app,
        Settings(_env_file=None, app_env="development", llm_provider="demo"),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/v1/voice/live") as websocket:
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert "Gemini provider" in message["message"]


def test_live_route_streams_mic_pcm_and_returns_egyptian_audio_and_transcripts() -> None:
    session = FakeLiveSession()
    fake_client = FakeLiveClient(session)
    app = FastAPI()

    def create_fake_client(*, api_key: str) -> FakeLiveClient:
        assert api_key == "test-key-not-real"
        return fake_client

    add_live_voice_route(
        app,
        Settings(
            _env_file=None,
            app_env="development",
            llm_provider="gemini",
            llm_api_key="test-key-not-real",
        ),
        client_factory=create_fake_client,
        live_types=SimpleNamespace(Blob=FakeBlob, LiveConnectConfig=FakeLiveConnectConfig),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/v1/voice/live") as websocket:
            ready = websocket.receive_json()
            websocket.send_bytes(b"mic-pcm-chunk")
            input_text = websocket.receive_json()
            output_text = websocket.receive_json()
            audio = websocket.receive_bytes()
            complete = websocket.receive_json()

    assert ready == {"type": "ready", "model": LIVE_MODEL, "mode": "speech_to_speech"}
    assert fake_client.model == LIVE_MODEL
    assert fake_client.config is not None
    assert fake_client.config.values["response_modalities"] == ["AUDIO"]
    assert "Egyptian Arabic" in LIVE_SYSTEM_INSTRUCTION
    assert session.received_audio[0].data == b"mic-pcm-chunk"
    assert session.received_audio[0].mime_type == "audio/pcm;rate=16000"
    assert input_text["type"] == "input_transcription"
    assert "دكتور قلب" in input_text["text"]
    assert output_text["type"] == "output_transcription"
    assert "أهلاً" in output_text["text"]
    assert audio == b"pcm-audio"
    assert complete["type"] == "turn_complete"
    assert fake_client.closed


class FakeTranscribeSession:
    def __init__(self) -> None:
        self.received_audio: list[FakeBlob] = []
        self.stream_ended = False
        self.input_done = asyncio.Event()

    async def send_realtime_input(
        self, *, audio: FakeBlob | None = None, audio_stream_end: bool = False
    ) -> None:
        if audio is not None:
            self.received_audio.append(audio)
        if audio_stream_end:
            self.stream_ended = True
            self.input_done.set()

    async def receive(self):
        yield SimpleNamespace(
            server_content=SimpleNamespace(
                interrupted=False,
                interim_input_transcription=SimpleNamespace(text="محتاج أحجز"),
                input_transcription=None,
                output_transcription=None,
                model_turn=None,
                turn_complete=False,
            ),
            go_away=None,
        )
        await self.input_done.wait()
        yield SimpleNamespace(
            server_content=SimpleNamespace(
                interrupted=False,
                interim_input_transcription=None,
                input_transcription=SimpleNamespace(text="محتاج أحجز موعد"),
                output_transcription=None,
                model_turn=None,
                turn_complete=True,
            ),
            go_away=None,
        )


def test_transcribe_route_streams_mic_pcm_and_returns_dictation() -> None:
    session = FakeTranscribeSession()
    fake_client = FakeLiveClient(session)  # type: ignore[arg-type]
    app = FastAPI()

    def create_fake_client(*, api_key: str) -> FakeLiveClient:
        assert api_key == "test-key-not-real"
        return fake_client

    add_live_voice_route(
        app,
        Settings(
            _env_file=None,
            app_env="development",
            llm_provider="gemini",
            llm_api_key="test-key-not-real",
        ),
        client_factory=create_fake_client,
        live_types=SimpleNamespace(Blob=FakeBlob, LiveConnectConfig=FakeLiveConnectConfig),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/v1/voice/transcribe") as websocket:
            ready = websocket.receive_json()
            websocket.send_bytes(b"dictation-pcm-chunk")
            interim = websocket.receive_json()
            websocket.send_json({"type": "stop"})
            final = websocket.receive_json()
            done = websocket.receive_json()

    assert ready == {
        "type": "ready",
        "model": "gemini-3.5-transcribe-live",
        "mode": "speech_to_text",
    }
    assert fake_client.config is not None
    assert fake_client.config.values["response_modalities"] == ["TEXT"]
    assert interim == {"type": "dictation_interim", "text": "محتاج أحجز"}
    assert final == {"type": "dictation_final", "text": "محتاج أحجز موعد"}
    assert done == {"type": "dictation_done"}
    assert session.stream_ended
    assert fake_client.closed