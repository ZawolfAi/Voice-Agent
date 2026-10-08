from typing import Literal

from pydantic import BaseModel


BookingAction = Literal["book", "modify", "cancel", "unknown"]
ConfirmationIntent = Literal["confirm", "reject", "unknown"]


class BookingExtraction(BaseModel):
    action: BookingAction = "unknown"
    confirmation: ConfirmationIntent = "unknown"
    specialty: str | None = None
    date: str | None = None
    time: str | None = None
    appointment_id: str | None = None
    reason: str | None = None
