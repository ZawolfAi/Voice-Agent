# CareOS Implementation Information

Last reviewed: 2026-09-25

This document is the implementation status of the CareOS repository. It separates verified behavior from provider abstractions and external production work. A feature is not marked production-complete only because a screen or endpoint exists.

## 1. Repository Architecture

### Frontend

- Framework: React + TypeScript + Vite.
- Build scripts:
  - `npm run typecheck`
  - `npm run build`
  - `npm run test:e2e`
- Frontend API access is centralized in `src/api.ts` and `src/api/*.ts`.
- Application shell and auth bootstrap are in:
  - `src/app/AppShell.tsx`
  - `src/app/authBootstrap.ts`
  - `src/app/routes.ts`
- Workspace navigation and role policy are in `src/features/workspace/navigation.ts`.
- Reusable UI components exist under `src/app/components`.
- Main design styles are in `src/styles.css`.

### Backend

- Framework: FastAPI.
- ORM: SQLAlchemy async.
- Database migrations: Alembic.
- Local test database: SQLite with `aiosqlite`.
- Intended production database: PostgreSQL with `asyncpg`.
- Authentication: password hashing with Argon2, JWT access tokens, persisted auth sessions, token revocation.
- Authorization: organization-scoped RBAC with `Role`, `Permission`, `UserRole`, and `RolePermission`.
- Backend API owner: `backend/app/api.py`.
- Models: `backend/app/models.py`.
- Auth and session logic: `backend/app/auth.py`.
- RBAC catalog and policy: `backend/app/rbac.py`.
- Storage: `backend/app/storage.py`.
- Providers: `backend/app/integrations.py`, `backend/app/saml.py`.
- Workers: `backend/app/worker.py`.

### Deployment

- Docker Compose defines:
  - `web`
  - `api`
  - `postgres`
  - `worker`
- The worker handles queued email and transcription jobs.
- Deployment secrets must be supplied through the environment or a secrets manager.

## 2. Database and Migrations

The migration chain currently ends at:

- `0001_identity_and_audit.py`
- `0002_clinical_core.py`
- `0003_document_storage.py`
- `0004_document_review.py`
- `0005_rbac_entities.py`
- `0006_clinical_workflow_foundation.py`
- `0007_auth_recovery_and_mfa.py`
- `0008_profiles_and_sso_configuration.py`
- `0009_email_jobs_and_soft_delete.py`
- `0010_transcript_versions.py`
- `0011_transcription_jobs.py`
- `0012_document_encounter_link.py`
- `0013_mfa_recovery_codes.py`

### Implemented entities

- `Organization`
- `User`
- `Role`
- `Permission`
- `UserRole`
- `RolePermission`
- `TeamInvite`
- `AuditEvent`
- `AuthSession`
- `PasswordResetToken`
- `EmailDeliveryJob`
- `Patient`
- `PatientProfile`
- `SSOConfiguration`
- `Encounter`
- `Appointment`
- `ClinicalNote`
- `ClinicalNoteVersion`
- `AudioFile`
- `Transcript`
- `TranscriptVersion`
- `TranscriptionJob`
- `PatientDocument`
- `PatientMessage`
- `PatientPortalAccount`
- `PatientPortalSession`
- `PatientPortalDocument`
- `Task`
- `CarePlan`
- `Notification`
- `ReminderJob`

### Database controls implemented

- Organization foreign keys on tenant-owned data.
- Unique organization-scoped role keys.
- Unique patient MRN within the intended tenant boundary.
- Indexes for organization, patient, user, encounter, and timestamps where applicable.
- Soft delete timestamps on sensitive resources.
- Clinical note version history.
- Transcript review version history.
- One-time reset and invitation token hashes.
- MFA recovery-code hashes.

### Database work still required

- Run the full Alembic chain against a clean PostgreSQL database.
- Validate PostgreSQL-specific types and constraints in CI.
- Add migration smoke tests to CI.
- Add backup, restore, and disaster-recovery drills.
- Add production data-retention jobs for all applicable resource classes.

## 3. Authentication

### Implemented

- Email/password registration.
- Email/password login.
- Argon2 password hashing.
- JWT access tokens.
- Persisted auth sessions.
- Logout and token revocation.
- Password reset request.
- Hashed, expiring, one-time password reset tokens.
- Session revocation after password reset.
- Invitation acceptance with hashed and expiring invitation tokens.
- Email verification endpoint.
- MFA enrollment using TOTP.
- Encrypted TOTP secret storage using Fernet derived from `SECRET_KEY`.
- MFA verification.
- MFA challenge during login.
- Ten one-time MFA recovery codes generated on enrollment.
- Recovery-code login support.
- Recovery-code regeneration endpoint.
- Production fail-fast if the default secret is used.
- Production fail-fast if SQLite is selected.
- Public registration cannot choose a privileged role.
- Staff roles are provisioned through controlled invitation/RBAC flows.

### Authentication APIs

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/password-reset/request`
- `POST /auth/password-reset/confirm`
- `POST /auth/invitations/accept`
- `POST /auth/verify-email`
- `POST /auth/logout`
- `POST /auth/mfa/enroll`
- `POST /auth/mfa/verify`
- `POST /auth/mfa/recovery-codes`
- `POST /auth/sso/start`
- `POST /auth/sso/callback`
- `POST /auth/sso`
- `GET /me`

### Authentication work still required

- Refresh-token rotation instead of access-token-only session lifecycle.
- MFA device management and explicit disable/revoke flow.
- MFA recovery support UX in the frontend.
- Account lockout and suspicious-login detection.
- Distributed rate limiting using Redis or another shared store.
- Production email delivery verification with a real SMTP provider.
- Production OIDC nonce/state/JWKS verification against a real identity provider.
- Production SAML metadata/signature testing with a real hospital IdP.

## 4. Multi-Tenancy

### Implemented

- Organization is created during registration.
- Authenticated users carry an organization relationship.
- Protected resources verify organization membership server-side.
- Frontend-provided organization IDs are not used as the authority for access.
- Patient portal tokens contain patient and organization claims and are checked against persisted records.
- Patient, encounter, recording, transcript, note, document, message, role, SSO, and audit flows are organization-scoped.
- Cross-organization tests exist for patient and encounter access.
- Staff role assignment is checked against the same organization.

### Work still required

- Formal endpoint-by-endpoint IDOR review with a matrix for every resource.
- Cross-tenant tests for every resource type, not only the current critical paths.
- PostgreSQL row-level security evaluation if required by deployment policy.
- Department/project relationship policy enforcement for every clinical resource.

## 5. RBAC and Permissions

### Implemented role families

- `admin`
- `doctor`
- `nurse`
- `receptionist`
- `hospital_director`
- `it_admin`
- `administrative_staff`
- `patient`

The catalog also supports aliases and future extensibility for additional roles.

### Implemented permission model

- `Role` is separate from `Permission`.
- `UserRole` assigns users to organization roles.
- `RolePermission` maps roles to permissions.
- Permission dependencies use assigned `RolePermission` records.
- Legacy permission fallback was removed.
- Login cannot escalate a user by sending a different role in the login payload.
- IT Admin does not receive clinical write permissions by default.
- Nurses and receptionists are restricted from physician-only approval flows unless explicitly assigned a permission.

### RBAC management APIs

- `GET /roles`
- `POST /roles`
- `GET /permissions`
- `POST /roles/{role_id}/permissions`
- `POST /users/{user_id}/roles`
- `POST /team/invites`

### Work still required

- Complete management UI for every RBAC administration operation.
- Explicit deny policy tests for every required role/resource pair.
- Permission catalog seed verification as part of Alembic deployment.
- Admin audit review for role and permission changes.

## 6. Frontend Route Protection and Dashboards

### Implemented

- Session-driven frontend permissions.
- Direct URL/hash protection.
- Role normalization for backend role names and aliases.
- Fail-closed route rendering.
- Logout clears role and permission state.
- Route guard E2E tests for doctor, nurse, receptionist, hospital director, IT admin, and administrative staff.
- Role-aware dashboard content and navigation.
- IT Admin dashboard avoids clinical panels by default.
- Director dashboard focuses on operational and security information.
- Clinical roles receive clinical workflow panels.
- Administrative and reception roles receive operational navigation.

### Dashboard-related views

- Main dashboard.
- Patients.
- Appointments.
- Clinical notes.
- Documents.
- Messages.
- Analytics.
- Reports.
- Departments.
- Team/audit.
- Integrations.
- Patient portal.
- Settings.

### Work still required

- Verify every dashboard card against a backend data contract.
- Remove any remaining informational placeholder text that implies unavailable integrations are active.
- Add role-specific dashboard API contracts instead of aggregating broad endpoints where appropriate.
- Add visual regression snapshots for every role.

## 7. Patient and Portal Workflow

### Implemented

- Patient creation through protected API.
- MRN/patient identifier support.
- Organization-scoped patient search.
- Search by name, MRN, and date of birth.
- Server-side pagination.
- Patient profile endpoint.
- Patient profile update endpoint.
- Dedicated patient portal login/session.
- Portal overview scoped to the authenticated patient.
- Portal appointments, messages, and approved documents.
- Portal message creation without accepting a frontend patient ID.
- Portal document download through authenticated API access.
- Approved-only patient document visibility.
- Mobile portal UI foundation.

### Patient and portal APIs

- `GET /patients`
- `POST /patients`
- `GET /patients/{patient_id}`
- `GET /patients/{patient_id}/profile`
- `PUT /patients/{patient_id}/profile`
- `PATCH /patients/{patient_id}`
- `POST /patient-portal/register`
- `POST /patient-portal/login`
- `GET /patient-portal/me`
- `GET /patient-portal/overview`
- `POST /patient-portal/messages`
- `POST /patient-portal/documents`
- `GET /patient-portal/documents/{document_id}/download`

### Work still required

- Full patient portal E2E workflow with a real patient account.
- Health-information and visit-detail screens with complete backend contracts.
- Patient self-service security UI.
- Notification delivery and read-state UX verification.

## 8. Appointments and Encounters

### Appointments implemented

- List appointments.
- Status filtering.
- Date-range filtering.
- Server-side pagination.
- Creation validation.
- Conflict detection.
- Cancellation.
- Rescheduling.
- Prevention of reopening cancelled appointments.
- Audit events for appointment mutations.

### Encounters implemented

- Create encounter from an authorized patient relationship.
- Get encounter by ID with tenant/resource checks.
- Start Encounter action from patient workflow.
- Server-side patient/organization/clinician linking.
- Active encounter linkage to notes and recordings.

### APIs

- `GET /appointments`
- `POST /appointments`
- `PATCH /appointments/{appointment_id}/status`
- `PATCH /appointments/{appointment_id}`
- `POST /encounters`
- `GET /encounters/{encounter_id}`

### Work still required

- Calendar provider integration if external calendars are required.
- Queue/check-in workflow completion for reception.
- More appointment conflict tests across departments and clinicians.
- Full encounter UI beyond the current start-and-notes flow.

## 9. Recording, STT, Transcripts, and Worker

### Recording implemented

- Browser `MediaRecorder` flow.
- Recording only under active encounter.
- Private storage keys.
- Server-side encounter/patient/organization linking.
- File type and size validation at storage boundary.
- Raw audio is not exposed as a public object URL.

### STT implemented

- `SpeechToTextProvider` boundary.
- `BelMasryProvider` configurable adapter.
- Configurable provider name and API URL/key.
- Default language `ar-EG`.
- Provider calls remain server-side.
- No fake transcript is generated when the provider is unavailable.
- Provider failure produces explicit failed state.

### Transcript implemented

- Transcript entity.
- Transcript status tracking.
- Transcript retrieval.
- Transcript review endpoint.
- Immutable transcript versions.
- Confidence and provider metadata.
- Manual review before clinical note drafting.

### Background worker implemented

- Durable `TranscriptionJob` entity.
- Queue status `QUEUED`.
- Processing status `PROCESSING`.
- Retry status `RETRY`.
- Terminal `COMPLETED` and `FAILED` states.
- Attempt count and backoff.
- Separate Compose worker service.
- Email and transcription jobs handled by `backend/app/worker.py`.

### APIs

- `POST /encounters/{encounter_id}/recordings`
- `GET /transcripts/{transcript_id}`
- `POST /recordings/{audio_id}/transcribe`
- `PATCH /transcripts/{transcript_id}/review`

### Work still required

- Real BelMasry credentials and production contract verification.
- Provider timeout, rate-limit, and webhook/callback handling.
- Real-time streaming implementation where the provider supports it.
- Medical vocabulary/context configuration.
- Code-switching and diarization validation with real Arabic clinical samples.
- Malware scanning before audio/document persistence.
- Audio retention deletion worker and deletion audit verification.

## 10. Clinical Notes, AI, Approval, PDF, and Documents

### Clinical notes implemented

- Clinical note draft creation.
- Draft update.
- AI draft field.
- AI summary provider boundary.
- Production guard against unconfigured AI sandbox use.
- Human review requirement.
- Approval/sign endpoint.
- Approved notes cannot be edited.
- Immutable `ClinicalNoteVersion` records.
- Version history endpoint.

### AI limitations

- The provider boundary exists.
- Development/test sandbox behavior exists.
- Production refuses unconfigured AI.
- A real production AI provider, grounded clinical prompting, citations, prompt-injection defense, PHI policy, and clinician review governance are still required.

### PDF and document delivery implemented

- PDF generation after approved note only.
- PDF includes organization, patient, MRN, clinician, note, and timestamp information.
- PDF stored through private storage abstraction.
- Document linked to patient and encounter.
- Download authorization and audit event.
- Patient portal exposes approved documents only.
- `reportlab` is declared and installed for local testing.

### APIs

- `POST /clinical-notes`
- `PATCH /clinical-notes/{note_id}`
- `POST /clinical-notes/{note_id}/summary`
- `POST /clinical-notes/{note_id}/approve`
- `POST /clinical-notes/{note_id}/sign`
- `GET /clinical-notes/{note_id}/versions`
- `POST /clinical-notes/{note_id}/document`
- `POST /patients/{patient_id}/documents`
- `PATCH /patients/{patient_id}/documents/{document_id}/review`
- `GET /patients/{patient_id}/documents/{document_id}/download`

### Work still required

- PDF visual snapshot verification across desktop/mobile.
- Document malware scanning and content disarm/sandboxing.
- External object storage signed URL verification with S3.
- Document sharing/notification policy implementation.
- AI provider production integration and clinical safety review.

## 11. Audit and Security

### Audit implemented

Audit events are written server-side for many actions, including:

- Sign-in and sign-out.
- Organization changes.
- Role and permission changes.
- Invitations.
- Patient creation/update/profile changes.
- Appointment creation/status/rescheduling.
- Encounter creation.
- Recording upload.
- Transcript review.
- Clinical note creation/update/summary/approval.
- Document generation/review/download.
- Portal account/message actions.
- MFA enablement and recovery-code regeneration.

### Security controls implemented

- Password hashing.
- JWT verification and revocation.
- Organization/resource authorization.
- Permission dependencies.
- Security response headers.
- Request IDs.
- Production secret validation.
- Production PostgreSQL requirement.
- Production-only auth rate limiting.
- Upload content type and size checks.
- Private storage key validation.
- Soft deletion on sensitive records.
- OIDC/SAML provider boundaries.
- Encrypted MFA secrets and hashed recovery codes.

### Security work still required

- Redis-backed distributed rate limiting.
- ClamAV or a managed malware scanning service.
- Full IDOR matrix against all 81 API routes.
- CSRF decision and implementation for cookie-based future sessions.
- Dependency/SAST/DAST/container scanning in CI.
- Penetration testing.
- Threat model and privacy impact assessment.
- Incident response and disaster recovery runbooks.
- Encrypted backup and restore drills.
- PHI-safe logging and telemetry audit.

## 12. Testing and Verification

### Confirmed local results

- Backend regression suite: `34 passed`.
- One upstream deprecation warning from Starlette/AnyIO remains.
- Frontend TypeScript typecheck: passed.
- Frontend production build: passed.
- Backend compile: passed.
- Full Playwright suite: `16 passed`.
- Role matrix E2E: `6 passed`.
- Mobile overflow smoke test: passed.
- Doctor direct-route protection: passed.
- Arabic/English language test: passed.
- PDF/version/audit download workflow: passed.
- Security header smoke test: passed.

### Test environment limitations

- Full PostgreSQL/Docker runtime validation has not been completed in this workspace.
- Real external provider credentials are not available.
- Accessibility tooling has not been run as a formal automated audit.
- Visual snapshots across every requested viewport have not been generated.

## 13. Responsive and Accessibility Status

### Verified

- Mobile overflow smoke test at 390px.
- Playwright browser execution with clean API/Vite servers.
- Mobile navigation and route behavior exist.
- TypeScript and production build pass.

### Still required

Run browser checks at all requested sizes:

- 320px
- 360px
- 375px
- 390px
- 393px
- 414px
- 430px
- 768px
- 820px
- 1024px
- 1280px
- 1440px
- 1920px

Also check:

- Safe-area insets.
- Keyboard navigation.
- Focus visibility.
- Screen-reader labels.
- Touch target minimums.
- Long patient names and document names.
- PDF preview on narrow screens.
- Recording controls on mobile.
- Error and toast overflow.

## 14. External Connections Still Needed

| Area | Current state | Required connection |
|---|---|---|
| PostgreSQL | Configured in Compose, not fully validated here | Running PostgreSQL service and clean migration test |
| BelMasry STT | Configurable adapter | API URL, API key, provider contract, Arabic clinical test data |
| AI | Configurable provider boundary | Production model endpoint, key, PHI policy, grounded prompts |
| SMTP | Queued email worker | SMTP credentials, domain verification, delivery monitoring |
| S3/object storage | Storage abstraction | Private bucket, IAM/workload identity, signed URL policy |
| SAML | `python3-saml` provider boundary | Signed IdP metadata and hospital IdP test environment |
| OIDC | Provider adapter | Issuer, client, audience, JWKS, nonce/state integration |
| Redis | Not connected | Distributed rate-limit store and optional job coordination |
| Malware scanning | Not connected | ClamAV or managed scanning API |
| Observability | Basic request IDs/metrics endpoint | PHI-safe logs, alerts, tracing, dashboards |

## 15. Final Status

### Functionally verified locally

The repository now has a connected workflow for:

`Login -> Patient Search -> Start Encounter -> Secure Recording -> Queued Transcription -> Transcript Review -> Clinical Note Draft -> AI Draft Boundary -> Doctor Approval -> Versioned Note -> PDF -> Secure Download -> Patient Portal -> Audit Event`

### Not production-ready until these gates are completed

1. PostgreSQL clean deployment and migration verification.
2. Real external provider credentials and contract tests.
3. Distributed rate limiting.
4. Malware scanning.
5. Full IDOR/security review.
6. Formal accessibility and all-viewport QA.
7. SAST/DAST, dependency, container, and penetration testing.
8. Backup/restore and incident-response validation.

The local application and test suite are in a strong verified development state. Production PHI use must wait for the gates above.
