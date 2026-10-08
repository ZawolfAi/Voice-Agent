from typing import Literal
from pydantic import BaseModel

FollowUpAction = Literal["create", "get", "modify", "cancel", "complete", "unknown"]
ConfirmationIntent = Literal["confirm", "reject", "unknown"]

class FollowUpExtraction(BaseModel):
    action: FollowUpAction = "unknown"
    confirmation: ConfirmationIntent = "unknown"
    followup_type: str | None = None
    date: str | None = None
    time: str | None = None
    appointment_id: str | None = None
    followup_id: str | None = None
    reason: str | None = None
