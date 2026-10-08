"""RBAC and role/permission definitions for CareOS.

This is the single source of truth for mapped roles, permissions, and the
organization-scoped access policy used by the clinical workspace.
"""

from __future__ import annotations

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "dashboard.read",
        "patient.read",
        "patient.write",
        "appointment.read",
        "appointment.write",
        "medical.summary",
        "clinical.note",
        "team.read",
        "team.invite",
        "organization.update",
        "audit.read",
        "analytics.read",
        "roles.view",
        "roles.assign",
        "roles.manage",
        "permissions.view",
        "users.invite",
        "patients.create",
        "clinical_notes.create",
        "clinical_notes.approve",
        "encounters.create", "encounters.view", "recordings.create", "recordings.view", "transcripts.create", "transcripts.view", "transcripts.update",
    },
    "doctor": {
        "dashboard.read",
        "patient.read",
        "patient.write",
        "appointment.read",
        "appointment.write",
        "medical.summary",
        "clinical.note",
        "analytics.read",
        "patients.create",
        "clinical_notes.create",
        "clinical_notes.approve",
        "encounters.create", "encounters.view", "recordings.create", "recordings.view", "transcripts.create", "transcripts.view", "transcripts.update",
    },
    "nurse": {
        "dashboard.read",
        "patient.read",
        "patient.write",
        "appointment.read",
        "clinical.note",
        "medical.summary",
        "patients.create",
        "clinical_notes.create",
        "encounters.view", "recordings.view", "transcripts.view", "transcripts.update",
    },
    "receptionist": {
        "dashboard.read",
        "patient.read",
        "appointment.read",
        "appointment.write",
        "team.read",
    },
    "patient": {
        "dashboard.read",
        "patient.read",
        "appointment.read",
        "medical.summary",
    },
}

ROLE_ALIASES: dict[str, str] = {
    "administrator": "admin",
    "admin": "admin",
    "physician": "doctor",
    "doctor": "doctor",
    "nurse": "nurse",
    "care_coordinator": "receptionist",
    "receptionist": "receptionist",
    "patient": "patient",
    "hospital_director": "hospital_director",
    "director": "hospital_director",
    "it_admin": "it_admin",
    "it_administrator": "it_admin",
    "administrative_staff": "administrative_staff",
    "staff": "administrative_staff",
}

ROLE_PERMISSIONS.update({
    "admin": ROLE_PERMISSIONS["admin"] | {
        "dashboard.read", "patients.search", "patients.view", "patients.create", "patients.update", "appointments.view", "appointments.create", "appointments.update",
        "clinical_notes.create", "clinical_notes.view", "clinical_notes.update", "clinical_notes.approve", "documents.create", "documents.download",
        "encounters.create", "encounters.view", "recordings.create", "recordings.view", "transcripts.create", "transcripts.view", "transcripts.update",
        "users.view", "audit_logs.view", "hospital.settings.view", "hospital.settings.manage", "roles.view", "roles.assign", "roles.manage", "permissions.view",
        "sso.view", "sso.manage",
        "analytics.view", "reports.view", "patient.read", "patient.write", "clinical.note", "medical.summary",
    },
    "doctor": ROLE_PERMISSIONS["doctor"] | {
        "dashboard.read", "patients.search", "patients.view", "patients.create", "patients.update", "appointments.view", "appointments.create", "appointments.update",
        "clinical_notes.create", "clinical_notes.view", "clinical_notes.update", "clinical_notes.approve", "documents.create", "documents.download",
        "encounters.create", "encounters.view", "recordings.create", "recordings.view", "transcripts.create", "transcripts.view", "transcripts.update",
        "patient.read", "patient.write", "analytics.view", "clinical.note", "medical.summary",
    },
    "nurse": ROLE_PERMISSIONS["nurse"] | {
        "dashboard.read", "patients.search", "patients.view", "patients.create", "patients.update", "appointments.view", "appointments.create", "appointments.update",
        "clinical_notes.create", "clinical_notes.view", "clinical_notes.update", "documents.create", "encounters.view", "recordings.view", "transcripts.view",
        "patient.read", "patient.write", "clinical.note", "medical.summary",
    },
    "receptionist": ROLE_PERMISSIONS["receptionist"] | {
        "patients.search", "patients.view", "appointments.view", "appointments.create", "appointments.update",
    },
    "hospital_director": {
        "dashboard.read", "users.view", "users.create", "users.update", "users.disable", "users.invite",
        "roles.view", "roles.assign", "roles.manage", "reports.view", "analytics.view", "audit_logs.view",
        "hospital.view", "hospital.settings.view", "hospital.settings.manage", "departments.view", "departments.manage",
        "patients.search", "patients.view", "patient.read",
    },
    "it_admin": {
        "dashboard.read", "users.view", "users.create", "users.update", "users.disable", "users.invite",
        "roles.view", "roles.assign", "permissions.view", "sso.view", "sso.manage", "security.view", "audit_logs.view",
    },
    "administrative_staff": {
        "dashboard.read", "appointments.view", "appointments.create", "appointments.update",
        "patients.search", "patients.view", "patients.demographics.view", "checkin.create", "checkin.view",
        "departments.view", "reports.operational.view",
    },
})

ROLE_SECTION_ACCESS: dict[str, set[str]] = {
    "admin": {"dashboard", "patients", "appointments", "team", "audit", "clinical", "analytics", "reports", "messages", "portal", "settings"},
    "doctor": {"dashboard", "patients", "appointments", "clinical", "analytics", "messages", "portal", "settings"},
    "nurse": {"dashboard", "patients", "appointments", "clinical", "messages", "portal", "settings"},
    "receptionist": {"dashboard", "patients", "appointments", "messages", "portal", "settings"},
    "patient": {"portal", "appointments", "messages", "settings"},
    "hospital_director": {"dashboard", "patients", "appointments", "team", "audit", "analytics", "reports", "settings"},
    "it_admin": {"dashboard", "team", "audit", "settings"},
    "administrative_staff": {"dashboard", "patients", "appointments", "reports", "settings"},
}

PERMISSION_MATRIX: dict[str, list[str]] = {
    "dashboard": ["dashboard.read"],
    "patients": ["patient.read", "patient.write"],
    "appointments": ["appointment.read", "appointment.write"],
    "team": ["team.invite", "team.read"],
    "audit": ["audit.read"],
    "clinical": ["clinical.note", "medical.summary"],
    "analytics": ["analytics.read"],
    "messages": ["patient.read"],
    "portal": ["patient.read"],
    "reports": ["analytics.read"],
}


def normalize_role(role: str | None) -> str:
    if not role:
        return "doctor"
    canonical = str(role).strip().lower().replace(" ", "_")
    return ROLE_ALIASES.get(canonical, canonical)


def permissions_for_role(role: str | None) -> list[str]:
    normalized = normalize_role(role)
    return sorted(ROLE_PERMISSIONS.get(normalized, set()))


def require_permission(permission: str, role: str) -> bool:
    """Return whether a role is allowed to perform the target permission."""
    normalized = normalize_role(role)
    permissions = ROLE_PERMISSIONS.get(normalized, set())
    aliases = {
        "patients.create": "patient.write",
        "patients.update": "patient.write",
        "clinical_notes.create": "clinical.note",
        "clinical_notes.update": "clinical.note",
        "clinical_notes.approve": "clinical_notes.approve",
        "users.invite": "team.invite",
        "appointments.create": "appointment.write",
        "appointments.update": "appointment.write",
        "appointments.view": "appointment.read",
        "documents.create": "patient.write",
        "documents.view": "patient.read",
        "documents.download": "patient.read",
        "audit_logs.view": "audit.read",
        "hospital.settings.manage": "organization.update",
    }
    return permission in permissions or aliases.get(permission) in permissions


def has_any_role(role: str | None, *allowed_roles: str) -> bool:
    """Check whether a user role matches one of the allowed roles after normalization."""
    normalized_role = normalize_role(role)
    normalized_allowed = {normalize_role(candidate) for candidate in allowed_roles}
    return normalized_role in normalized_allowed


def can_access_section(role: str | None, section: str) -> bool:
    """Return whether a normalized role is allowed to access a section."""
    normalized = normalize_role(role)
    allowed = ROLE_SECTION_ACCESS.get(normalized, set())
    return section in allowed


def can_access_patient_scope(
    role: str | None,
    action: str,
    same_organization: bool,
    same_department: bool = True,
    same_project: bool = True,
) -> bool:
    """Enforce patient-scoped access for clinical workflows, including department/project boundaries.

    The first production guard is organization-level isolation, but the policy is designed to
    fail closed when a caller lacks the required department/project match.
    """
    if not same_organization or not same_department or not same_project:
        return False
    normalized = normalize_role(role)
    action = action.lower().strip()
    if normalized == "admin":
        return action in {"read", "write", "notes", "appointments", "documents"}
    if normalized == "doctor":
        return action in {"read", "write", "notes", "appointments", "documents"}
    if normalized == "nurse":
        return action in {"read", "write", "notes", "appointments", "documents"}
    if normalized == "receptionist":
        return action in {"read", "appointments"}
    if normalized == "patient":
        return action in {"read"}
    if normalized in {"hospital_director", "it_admin", "administrative_staff"}:
        return action in {"read", "appointments"} if normalized != "it_admin" else False
    return False


def can_access_patient_resource(role: str | None, permission: str) -> bool:
    """Alias for permission checks used by patient-sensitive resources."""
    return require_permission(permission, normalize_role(role))


def get_missing_policy(role: str, permission: str) -> str:
    """Return a human-readable policy note for teams that finish the project later."""
    return f"Missing RBAC policy: role={normalize_role(role)} permission={permission}"
