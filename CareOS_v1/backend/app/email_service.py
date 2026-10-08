import asyncio
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import EmailDeliveryJob

settings = get_settings()


async def _send(message: EmailMessage) -> bool:
    if not settings.smtp_host or not settings.smtp_from:
        return False

    def send() -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)

    for attempt in range(max(1, settings.email_max_retries)):
        try:
            await asyncio.to_thread(send)
            return True
        except (OSError, smtplib.SMTPException):
            if attempt + 1 == max(1, settings.email_max_retries):
                return False
            await asyncio.sleep(settings.email_retry_backoff_seconds * (2**attempt))
    return False


async def send_team_invite(email: str, organization_name: str, role: str, token: str | None = None) -> bool:
    message = EmailMessage()
    message["Subject"] = f"CareOS invitation to {organization_name}"
    message["From"] = settings.smtp_from
    message["To"] = email
    activation = f"{settings.app_url}/#accept-invitation?token={token}" if token else "Sign in to CareOS to accept your invitation."
    message.set_content(f"You have been invited to join {organization_name} on CareOS as {role}.\n\n{activation}")
    return await _send(message)


async def send_password_reset(email: str, token: str) -> bool:
    message = EmailMessage()
    message["Subject"] = "CareOS password reset"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(f"Reset your CareOS password using this link: {settings.app_url}/#reset-password?token={token}")
    return await _send(message)


async def enqueue_email(session: AsyncSession, *, recipient: str, subject: str, body: str, organization_id=None) -> EmailDeliveryJob:
    job = EmailDeliveryJob(organization_id=organization_id, recipient=recipient, subject=subject, body=body)
    session.add(job)
    await session.flush()
    return job


async def process_email_jobs(session: AsyncSession, limit: int = 20) -> int:
    jobs = (await session.scalars(select(EmailDeliveryJob).where(EmailDeliveryJob.status == "queued", EmailDeliveryJob.available_at <= datetime.now(timezone.utc)).order_by(EmailDeliveryJob.created_at).limit(limit))).all()
    processed = 0
    for job in jobs:
        job.status = "sending"
        job.attempts += 1
        await session.flush()
        message = EmailMessage()
        message["Subject"] = job.subject
        message["From"] = settings.smtp_from
        message["To"] = job.recipient
        message.set_content(job.body)
        sent = await _send(message)
        if sent:
            job.status = "sent"
            job.sent_at = datetime.now(timezone.utc)
        else:
            job.status = "failed" if job.attempts >= settings.email_max_retries else "queued"
            job.last_error = "SMTP delivery failed"
        processed += 1
    await session.commit()
    return processed
