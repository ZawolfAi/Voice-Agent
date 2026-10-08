"""Validated structured information extracted from a single patient turn."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from voice_agent.app.schemas.requests import Intent


class IntentExtraction(BaseModel):
    """LLM output. Date/time expressions are normalized by application code."""

    model_config = ConfigDict(extra="forbid")

    intent: Intent
    availability_only: bool = False
    specialty: str | None = Field(default=None, max_length=80)
    date_expression: str | None = Field(default=None, max_length=80)
    preferred_time: str | None = Field(default=None, max_length=80)
    appointment_id: str | None = Field(default=None, max_length=100)

    @field_validator("specialty", "date_expression", "preferred_time", "appointment_id")
    @classmethod
    def reject_blank_values(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("extracted values must be non-empty or null")
        return value.strip() if value is not None else None


class ExtractionContext(BaseModel):
    """Minimal context passed to the model; excludes patient/session identifiers."""

    current_date: str
    current_intent: Intent | None = None
    collected_parameters: dict[str, str] = Field(default_factory=dict)