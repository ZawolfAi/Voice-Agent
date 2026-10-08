# CareOS Production Implementation Plan

## Product decision

CareOS is a clinician decision-support system. It does not diagnose, prescribe, or autonomously act on a patient's behalf. Every AI output remains a draft or suggestion until a clinician reviews it.

## Phase 0: foundation and threat model

- Separate web, API, workers, and infrastructure concerns.
- Define synthetic-data-only local development and a no-PHI policy until privacy controls are signed off.
- Threat model: broken access control, leaked PHI, prompt injection, unsafe model output, malicious uploads, replayed sessions, and audit tampering.
- Add CI checks for formatting, type checking, dependency vulnerabilities, secrets, and tests.

## Current execution status

The repository is being migrated to the requested 24-phase Care architecture. Phase 1 analysis identified FastAPI, SQLAlchemy/Alembic, React/Vite, JWT sessions, hash-based frontend routes, private filesystem/S3 storage, and an existing patient portal. Phase 2 has started with migration `0005_rbac_entities`; the automatic demo account and synthetic patient seeding were removed.

The following legacy behavior is explicitly retired: development login fallback for `dr.rana@citycare.org`, automatic patient records during registration, and frontend authentication success when the API is unavailable.

## Phase 1: secure clinical API

- FastAPI service with strict CORS, security headers, request IDs, structured error responses, health/readiness checks, and environment validation.
- PostgreSQL with SQLAlchemy/Alembic, UTC timestamps, soft-delete policy, tenant/organization boundaries, and encrypted backups.
- OIDC/SAML hospital identity integration. Local development uses an explicit synthetic-user mode only.
- Server-side RBAC: normalized roles and permissions with organization-scoped assignments. Every patient, note, appointment, and AI request must be authorized server-side.
- Append-only audit events for login, patient access, record edits, exports, and AI actions. Never log raw PHI or prompts by default.

## Phase 2: clinical workflows

- Patients: paginated search, profile, records, vitals, labs, medications, and access history.
- Appointments: conflict-aware scheduling, status transitions, reminder jobs, and idempotent writes.
- Notes: autosave drafts, explicit clinician sign-off, version history, and immutable signed versions.
- Frontend data access through a typed API client with loading/error/empty states. No patient data embedded in the client bundle.

## Phase 3: AI services

- Provider-agnostic LLM interface behind the API; model keys stay server-side.
- RAG pipeline: approved protocol registry, document versioning, tenant filters, retrieval limits, citation IDs, and grounded-answer checks.
- Prompt-injection defenses for retrieved documents and user uploads. Reject unsupported claims and show missing evidence clearly.
- AI telemetry: latency, retrieval quality, citation coverage, clinician feedback, and refusal rate without storing unnecessary PHI.
- Human approval gate before an AI summary can become part of a medical record.

## Phase 4: documents and operations

- Isolated OCR worker for scanned records with file validation, malware scanning, quarantine, and human verification.
- Background jobs for reminders and delayed lab follow-ups with retries, idempotency keys, and dead-letter handling.
- Observability with redacted logs, metrics, traces, alerts, and uptime checks.
- Deployment with private networking, managed secrets, TLS, database backups, restore drills, and separate staging/production environments.

## Release gates

1. No unresolved high or critical security findings.
2. Authorization tests cover every patient-facing endpoint.
3. Audit events are generated for all sensitive operations.
4. AI answers display sources, limitations, and the clinician-only disclaimer.
5. Clinical notes require review before persistence as a signed record.
6. Synthetic end-to-end demo passes without external secrets.
7. Privacy, retention, incident response, and backup procedures are approved.

## Removed from the product scope

- Patient portal and direct-to-patient consultation.
- Manager KPI dashboard and department analytics.
- Decorative quick actions and non-clinical widgets.
- Autonomous diagnosis, prescribing, or patient messaging without clinician approval.
