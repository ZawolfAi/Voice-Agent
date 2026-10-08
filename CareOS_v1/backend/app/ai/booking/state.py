from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


BookingAction = Literal["book", "modify", "cancel", "unknown"]
BookingStatus = Literal[
    "new",
    "collecting",
    "confirming",
    "executing",
    "completed",
    "failed",
]


@dataclass
class BookingState:
    # Conversation context
    patient_id: str | None = None
    conversation_id: str | None = None
    raw_text: str = ""

    # Intent
    action: BookingAction = "unknown"

    # Booking data
    appointment_id: str | None = None
    target_date: str | None = None
    starts_at: datetime | None = None
    specialty: str | None = None
    reason: str | None = None

    # Availability
    available_slots: list[str] | None = None
    selected_slot: str | None = None

    # Workflow
    status: BookingStatus = "new"
    missing_fields: list[str] = field(default_factory=list)
    awaiting_confirmation: bool = False

    # Result / error
    result: dict[str, object] | None = None
    error: str | None = None


def build_booking_state(
    extraction,
    *,
    patient_id: str | None = None,
    conversation_id: str | None = None,
    timezone: str = "Africa/Cairo",
    now: datetime | None = None,
) -> BookingState:
    from zoneinfo import ZoneInfo
    from app.ai.booking.normalizer import NormalizationError, normalize_datetime, _normalize_date

    state = BookingState(
        patient_id=patient_id,
        conversation_id=conversation_id,
        action=extraction.action,
        appointment_id=extraction.appointment_id,
        specialty=extraction.specialty,
        reason=extraction.reason,
        status="collecting",
    )

    if extraction.date:
        try:
            tz = ZoneInfo(timezone)
            current = now or datetime.now(tz)
            state.target_date = _normalize_date(extraction.date, current).isoformat()
        except NormalizationError as exc:
            state.error = str(exc)

    if extraction.date and extraction.time:
        try:
            state.starts_at = normalize_datetime(
                extraction.date,
                extraction.time,
                timezone,
                now=now,
            )
        except NormalizationError as exc:
            state.error = str(exc)

    return state


def update_missing_fields(state: BookingState) -> BookingState:
    missing: list[str] = []

    if state.action == "unknown":
        missing.append("action")
    elif not state.patient_id:
        missing.append("patient_id")

    if state.action == "book":
        if not state.specialty:
            missing.append("specialty")

        if state.starts_at:
            pass  # Exact time provided
        else:
            if not state.target_date:
                missing.append("date_time")
            elif state.available_slots is None:
                missing.append("available_slots")
            elif not state.selected_slot:
                missing.append("selected_slot")

        if not state.reason:
            missing.append("reason")

    elif state.action in {"modify", "cancel"}:
        if not state.appointment_id:
            missing.append("appointment_id")

        if state.action == "modify" and not state.starts_at:
            missing.append("date_time")

    state.missing_fields = missing
    return state
