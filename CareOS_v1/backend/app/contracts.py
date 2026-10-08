"""API contract placeholders for the CareOS real backend architecture.

This file is intentionally a contract-layer specification. It tells the
frontend and backend teams which request/response objects, route names,
and business objects are expected to exist for a production-grade CareOS
implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class AuthUserContract:
    id: UUID
    organization_id: UUID
    workspace_id: UUID | None
    email: str
    full_name: str
    role: str
    onboarding_complete: bool


@dataclass(frozen=True)
class OrganizationWorkspaceContract:
    organization_id: UUID
    workspace_id: UUID
    organization_name: str
    department: str
    timezone: str
    onboarding_complete: bool


@dataclass(frozen=True)
class DashboardContract:
    patient_count: int
    upcoming_appointments: list[dict[str, object]]
    followups: list[dict[str, object]]
    kpi: dict[str, object]


@dataclass(frozen=True)
class SSOStartRequest:
    provider: str
    email: str | None = None
    redirect_uri: str | None = None


@dataclass(frozen=True)
class SSOCallback:
    code: str
    state: str
    provider: str = "hospital_sso"


class CareOSContract:
    """Static mapping of an implementation contract.

    This is not a runtime API router; it is a contract card that future
    backend and frontend engineers can implement consistently.
    """

    AUTH_ENDPOINTS = {
        "register": "POST /auth/register",
        "login": "POST /auth/login",
        "login_sso": "POST /auth/sso",
        "me": "GET /me",
        "logout": "POST /auth/logout",
    }

    ORG_WORKSPACE_ENDPOINTS = {
        "get_me": "GET /me",
        "get_organization": "GET /organization",
        "get_workspace": "GET /workspace",
        "patch_organization": "PATCH /organization",
        "create_workspace": "POST /workspace",
    }

    CLINICAL_ENDPOINTS = {
        "dashboard": "GET /dashboard",
        "patients": "GET /patients",
        "patient_detail": "GET /patients/{patient_id}",
        "appointments": "GET /appointments",
        "team": "GET /team",
        "audit_events": "GET /audit-events",
    }

    REQUIRED_AUTH_USER_FIELDS = {
        "id",
        "organization_id",
        "workspace_id",
        "email",
        "full_name",
        "role",
        "onboarding_complete",
    }

    REQUIRED_ORGANIZATION_WORKSPACE_FIELDS = {
        "organization_id",
        "workspace_id",
        "organization_name",
        "department",
        "timezone",
        "onboarding_complete",
    }
