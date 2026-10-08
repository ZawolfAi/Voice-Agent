"""Background workers for queued CareOS jobs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .db import get_session, init_db
from .email_service import process_email_jobs
from .integrations import get_speech_to_text_provider
from .models import AudioFile, Transcript, TranscriptionJob
from .storage import StorageService


async def process_transcription_jobs(session) -> int:
    now = datetime.now(timezone.utc)
    job = await session.scalar(select(TranscriptionJob).where(TranscriptionJob.status.in_(["QUEUED", "RETRY"]), TranscriptionJob.available_at <= now).order_by(TranscriptionJob.created_at).limit(1))
    if job is None:
        return 0
    transcript = await session.get(Transcript, job.transcript_id)
    audio = await session.get(AudioFile, job.audio_file_id)
    if transcript is None or audio is None:
        job.status = "FAILED"
        job.last_error = "RECORDING_OR_TRANSCRIPT_NOT_FOUND"
        await session.commit()
        return 1
    job.status = "PROCESSING"
    job.attempts += 1
    transcript.status = "TRANSCRIBING"
    await session.commit()
    try:
        result = await get_speech_to_text_provider().transcribe(StorageService().read_document(audio.storage_key), language=transcript.language)
        transcript.status = "COMPLETED"
        transcript.transcript_text = str(result.get("text") or "")
        transcript.confidence = result.get("confidence") if isinstance(result.get("confidence"), (int, float)) else None
        transcript.completed_at = datetime.now(timezone.utc)
        job.status = "COMPLETED"
        job.completed_at = datetime.now(timezone.utc)
        job.last_error = None
    except Exception as error:
        transcript.status = "FAILED" if job.attempts >= job.max_attempts else "TRANSCRIBING"
        transcript.error_code = "SPEECH_TO_TEXT_NOT_CONFIGURED" if "not configured" in str(error).lower() else "SPEECH_TO_TEXT_PROVIDER_ERROR"
        job.status = "FAILED" if job.attempts >= job.max_attempts else "RETRY"
        job.last_error = transcript.error_code
        job.available_at = datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** job.attempts))
    await session.commit()
    return 1


async def run_email_worker(interval_seconds: float = 2.0) -> None:
    await init_db()
    while True:
        async for session in get_session():
            await process_email_jobs(session)
            await process_transcription_jobs(session)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_email_worker())
