import asyncio
from types import SimpleNamespace
from typing import Any

from voice_agent.app.audio.tts import generate_speech_audio
from voice_agent.app.config import Settings


class FakeTTSPart:
    def __init__(self, data: bytes, mime_type: str = "audio/wav") -> None:
        self.inline_data = SimpleNamespace(data=data, mime_type=mime_type)


class FakeTTSResponse:
    def __init__(self, data: bytes) -> None:
        self.candidates = [
            SimpleNamespace(
                content=SimpleNamespace(parts=[FakeTTSPart(data)])
            )
        ]


class FakeTTSClient:
    def __init__(self, data: bytes = b"fake-wav-bytes") -> None:
        self.data = data
        self.aio = SimpleNamespace(
            models=SimpleNamespace(
                generate_content=self.generate_content
            )
        )

    async def generate_content(self, *, model: str, contents: str) -> FakeTTSResponse:
        del model, contents
        return FakeTTSResponse(self.data)


def test_generate_speech_audio_skips_when_no_api_key() -> None:
    settings = Settings(_env_file=None, app_env="development", llm_provider="gemini", llm_api_key=None)
    result = asyncio.run(generate_speech_audio("Hello", settings))
    assert result is None


def test_generate_speech_audio_skips_empty_text() -> None:
    settings = Settings(_env_file=None, app_env="development", llm_provider="gemini", llm_api_key="key")
    result = asyncio.run(generate_speech_audio("   ", settings))
    assert result is None


def test_generate_speech_audio_synthesizes_wav() -> None:
    settings = Settings(_env_file=None, app_env="development", llm_provider="gemini", llm_api_key="key")
    fake_client = FakeTTSClient(b"sample-audio-data")

    result = asyncio.run(
        generate_speech_audio("Hello world", settings, client_factory=lambda **kwargs: fake_client)
    )
    assert result is not None
    data, mime = result
    assert data == b"sample-audio-data"
    assert mime == "audio/wav"
