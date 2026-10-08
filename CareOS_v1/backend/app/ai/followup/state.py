from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.ai.followup.contracts import FollowUpAction

FollowUpStatus = Literal[
    "new",
    "collecting",
    "confirming",
    "executing",
    "completed",
    "failed",
]

@dataclass
class FollowUpState:
    # Conversation context
    patient_id: str | None = None
    conversation_id: str | None = None
    raw_text: str = ""

    # Intent
    action: FollowUpAction = "unknown"

    # FollowUp data
    appointment_id: str | None = None
    followup_id: str | None = None
    followup_type: str | None = None
    target_date: str | None = None
    due_at: datetime | None = None
    reason: str | None = None

    # Workflow
    status: FollowUpStatus = "new"
    missing_fields: list[str] = field(default_factory=list)
    awaiting_confirmation: bool = False

    # Result / error
    result: dict[str, object] | None = None
    error: str | None = None

def build_followup_state(
    extraction,
    *,
    patient_id: str | None = None,
    conversation_id: str | None = None,
    timezone: str = "Africa/Cairo",
    now: datetime | None = None,
) -> FollowUpState:
    from zoneinfo import ZoneInfo
    from app.ai.booking.normalizer import NormalizationError, normalize_datetime, _normalize_date

    state = FollowUpState(
        patient_id=patient_id,
        conversation_id=conversation_id,
        action=extraction.action,
        appointment_id=extraction.appointment_id,
        followup_id=extraction.followup_id,
        followup_type=extraction.followup_type,
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
            state.due_at = normalize_datetime(
                extraction.date,
                extraction.time,
                timezone,
                now=now,
            )
        except NormalizationError as exc:
            state.error = str(exc)

    return state

def update_missing_fields(state: FollowUpState) -> FollowUpState:
    missing: list[str] = []

    if state.action == "unknown":
        missing.append("action")
    elif not state.patient_id:
        missing.append("patient_id")

    if state.action == "create":
        if not state.followup_type:
            missing.append("followup_type")
        if not state.reason:
            missing.append("reason")
        if not state.due_at:
            missing.append("due_at")
            
    elif state.action in {"get", "modify", "cancel", "complete"}:
        if not state.followup_id:
            missing.append("followup_id")
            
        if state.action == "modify":
            if not state.due_at and not state.reason:
                missing.append("due_at_or_reason")

    state.missing_fields = missing
    return state
