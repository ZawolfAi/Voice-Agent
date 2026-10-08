"""Identity context passed only by an authenticated host/application boundary."""

from pydantic import BaseModel, ConfigDict, Field


class AuthenticatedUserContext(BaseModel):
    """Minimal host-asserted identity; constructing this is a trust-boundary action.

    Do not construct it from patient utterances or user-editable CLI input. The
    host must authenticate the user and resolve its trusted patient identifier.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    patient_id: str = Field(min_length=1, max_length=128)