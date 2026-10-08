"""Value objects used by the organization onboarding contract.

Persistence is intentionally owned by the API transaction in ``api.py`` so
workspace identifiers always come from the database.
"""

from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class WorkspacePlan:
    """Validated values for updating an existing organization workspace."""

    organization_name: str
    department: str
    timezone: str
    admin_email: str
