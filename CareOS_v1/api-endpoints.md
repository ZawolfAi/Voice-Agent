# CareOS API Endpoint Guide

Last reviewed: 2026-09-25

This file documents the current backend endpoints implemented in `backend/app/api.py`.

## Base Contract

Base URL:

```text
http://localhost:8000/api/v1
```

Authenticated staff request:

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

Patient portal request:

```http
Authorization: Bearer <patient_portal_token>
```

### Common response behavior

- `200`: successful read/update/action.
- `201`: resource created.
- `202`: asynchronous job accepted, especially transcription.
- `204`: successful action with no response body, such as logout.
- `400`: invalid state, expired token, invalid provider response, or invalid action.
- `401`: missing or invalid authentication.
- `403`: authenticated but missing permission.
- `404`: resource does not exist in the caller's organization or relationship scope.
- `409`: state conflict, duplicate resource, or invalid workflow transition.
- `422`: request validation failure.
- `429`: production authentication rate limit exceeded.
- `500`: sanitized internal error; stack traces must remain server-side.
- `503`: external provider unavailable or not configured.

The backend must derive organization membership from the authenticated session. Clients must not use a submitted `organization_id`, `role`, or `patient_id` as an authorization authority.

## Permission Names Used by the API

Examples used by protected dependencies:

- `users.view`, `users.invite`, `users.create`, `users.update`
- `roles.view`, `roles.assign`, `roles.manage`
- `permissions.view`
- `patients.search`, `patients.view`, `patients.create`, `patients.update`
- `appointments.view`, `appointments.create`, `appointments.update`
- `encounters.create`, `encounters.view`, `encounters.update`
- `recordings.create`, `recordings.view`
- `transcripts.create`, `transcripts.view`, `transcripts.update`
- `clinical_notes.create`, `clinical_notes.view`, `clinical_notes.update`, `clinical_notes.approve`
- `documents.create`, `documents.view`, `documents.download`
- `reports.view`, `analytics.view`, `audit_logs.view`
- `sso.view`, `sso.manage`
- `hospital.settings.view`, `hospital.settings.manage`
- `messages.self.view`, `messages.self.send`

## 1. System and Health

### GET /health

- Authentication: public.
- Purpose: liveness check.
- Response: `{ "status": "ok" }`.
- Does not query clinical data.

### GET /readiness

- Authentication: public.
- Purpose: checks application/database readiness.
- Response: readiness status.
- Use this endpoint for deployment health checks.

### GET /metrics

- Authentication: protected clinical/authorized user.
- Purpose: returns organization-scoped operational counters.
- Response may include patient count, appointment count, environment, SSO readiness, and deployment metadata.
- Must never expose PHI or cross-organization counts.

### GET /system/status

- Authentication: public system metadata endpoint.
- Purpose: reports application environment, deployment name, allowed hosts, CORS origins, and provider readiness flags.
- Secrets and API keys are never returned.

### POST /system/audit/cleanup

- Permission: `audit_logs.view`.
- Body: none.
- Purpose: removes audit events older than configured retention.
- Response: deleted count and configured retention days.
- Production use should be moved to a controlled scheduled job, not a user-triggered action.

## 2. Authentication and Sessions

### POST /auth/register

- Authentication: public.
- Purpose: creates a new organization and its first owner/admin account.
- Body:

```json
{
  "email": "owner@example.org",
  "password": "strong-password",
  "full_name": "Workspace Owner",
  "organization_name": "CityCare",
  "department": "General Medicine",
  "project": "Outpatient"
}
```

- The public role field is not trusted for privilege assignment. New staff roles must be assigned through invitation/RBAC flows.
- Response: access token, token type, and public user session.
- Side effects: organization creation, user creation, role assignment, audit event.

### POST /auth/login

- Authentication: public.
- Body: email, password, optional six-digit `mfa_code`, or one-time `mfa_recovery_code`.
- Response: access token and public user.
- If MFA is enabled and the second factor is absent/invalid, returns `401` with `MFA_REQUIRED`.
- Login role fields are not trusted for escalation.

### POST /auth/password-reset/request

- Authentication: public.
- Body: `{ "email": "user@example.org" }`.
- Response intentionally remains generic to avoid account enumeration.
- Creates a hashed, expiring, one-time reset token.
- Queues an email delivery job.
- Development may expose a development token; production must never expose it.

### POST /auth/password-reset/confirm

- Authentication: public with reset token.
- Body: `{ "token": "...", "password": "new-strong-password" }`.
- Invalidates the reset token after use.
- Revokes active sessions for the user.
- Returns reset confirmation.

### POST /auth/invitations/accept

- Authentication: public with invitation token.
- Body: token, full name, password.
- Creates a user in the invitation's organization.
- Uses the role stored server-side on the invitation.
- Does not accept an organization ID from the client.
- Marks the invitation accepted and returns a new session.

### POST /auth/verify-email

- Permission: current authenticated user.
- Body: `{ "email": "current-user@example.org" }`.
- Only the current account email may be verified.
- Writes an audit event.

### POST /auth/logout

- Permission: authenticated user.
- Body: none.
- Revokes the current JWT session.
- Response: `204`.

### GET /me

- Permission: authenticated user.
- Returns current user, organization, role, permissions, and onboarding state.
- Used by frontend auth bootstrap.

### POST /auth/mfa/enroll

- Permission: authenticated user.
- Creates an encrypted TOTP secret.
- Response includes an `otpauth://` URI and setup secret during enrollment.
- MFA remains disabled until verification succeeds.

### POST /auth/mfa/verify

- Permission: authenticated user.
- Body: `{ "code": "123456" }`.
- Enables MFA after valid TOTP verification.
- Generates one-time recovery codes.
- Stores only recovery-code hashes.
- Returns recovery codes once so the user can store them securely.

### POST /auth/mfa/recovery-codes

- Permission: authenticated user with MFA enabled.
- Body: none.
- Invalidates previous recovery codes.
- Generates and returns a new one-time set.
- Writes an audit event.

### POST /auth/sso/start

- Authentication: public.
- Body: provider, optional email, optional redirect URI.
- Response: provider, redirect URL, state, nonce.
- Redirect hosts are allowlisted.
- Production must use a real configured IdP.

### POST /auth/sso/callback

- Authentication: public provider callback.
- Body: provider, authorization code, state.
- Validates provider response and maps verified claims.
- Production must validate issuer, audience, signature, nonce, state, and expiry.
- Returns mapped claims and a CareOS session.

### POST /auth/sso

- Authentication: public/SSO exchange route.
- Purpose: alternative SSO identity exchange used by the current frontend adapter.
- Production must be connected to a real provider rather than development mock behavior.

## 3. Organization and Workspace

### GET /organization

- Permission: `hospital.settings.view`.
- Returns current organization name, department, timezone, and onboarding state.
- Organization is derived from the current user.

### GET /workspace

- Permission: `hospital.settings.view`.
- Returns workspace/organization configuration and current onboarding state.

### POST /workspace

- Permission: `hospital.settings.manage`.
- Body: name, department, timezone.
- Creates or completes workspace configuration.
- Writes an organization audit event.

### PATCH /organization

- Permission: `hospital.settings.manage`.
- Body: organization name, department, timezone.
- Updates only the current organization.
- Does not accept a target organization ID.

## 4. Team, Roles, Permissions, and SSO Configuration

### GET /team

- Permission: `users.view`.
- Returns users from the authenticated user's organization.
- Must not return users from other organizations.

### POST /team/invites

- Permission: `users.invite`.
- Body: email and approved role key.
- Creates a hashed, expiring invitation.
- Queues invitation email.
- Development may return a development token; production must not.

### GET /roles

- Permission: `roles.view`.
- Returns organization-scoped roles.

### POST /roles

- Permission: `roles.manage`.
- Body: role key, name, description.
- Creates a custom role inside the current organization.
- Role keys are unique per organization.

### GET /permissions

- Permission: `permissions.view` or role-management policy.
- Returns the available permission catalog.
- Does not grant permissions.

### POST /roles/{role_id}/permissions

- Permission: `roles.manage`.
- Body: `permission_id`.
- Grants a permission to a role in the same organization.
- Writes a role permission audit event.

### POST /users/{user_id}/roles

- Permission: `roles.assign`.
- Body: `role_id`.
- Assigns an organization role to a same-organization user.
- Must reject cross-organization user/role combinations.

### GET /organization/sso

- Permission: `sso.view`.
- Returns tenant-owned SSO configuration without secrets.

### PUT /organization/sso

- Permission: `sso.manage`.
- Body: provider, issuer/metadata settings, client details, redirect configuration.
- Stores sensitive client secrets encrypted.
- Writes an SSO configuration audit event.

### GET /audit-events

- Permission: `audit_logs.view`.
- Returns organization-scoped audit events.
- Audit events are created server-side.
- Never use a client-provided organization ID to select the audit tenant.

## 5. Notifications, Dashboard, Patients, and Appointments

### GET /notifications

- Permission: authenticated user.
- Returns notifications for the current user.

### PATCH /notifications/{notification_id}/read

- Permission: authenticated user.
- Marks only a notification belonging to the current user as read.

### GET /dashboard

- Permission: `dashboard.read`.
- Returns organization/role-scoped dashboard data.
- Clinical and administrative panels are filtered by permissions.

### GET /patients

- Permission: `patients.search` or equivalent clinical/admin permission.
- Query parameters:
  - `q`: name or MRN search.
  - `date_of_birth`: optional DOB filter.
  - `page`: one-based page.
  - `page_size`: bounded page size.
- Returns patients only from the current organization and non-deleted records.
- Response contains patient identity/basic demographic fields and pagination metadata.

### POST /patients

- Permission: `patients.create`.
- Body: MRN, given name, family name, date of birth, and approved demographic fields.
- Creates an organization-scoped patient.
- Writes a patient-created audit event.

### GET /patients/{patient_id}

- Permission: `patients.view`.
- Resource checks: organization, patient relationship, and policy scope.
- Returns basic patient data, notes/documents permitted for the caller, and relationship data.

### GET /patients/{patient_id}/profile

- Permission: patient profile/demographic view.
- Returns the patient profile for a same-organization patient.

### PUT /patients/{patient_id}/profile

- Permission: `patients.update` or demographic update policy.
- Body: approved profile fields.
- Writes a profile update audit event.

### PATCH /patients/{patient_id}

- Permission: `patients.update`.
- Body: approved patient demographic fields.
- Must not modify clinical notes or diagnoses.

### GET /appointments

- Permission: `appointments.view`.
- Query parameters:
  - `status`
  - `from_datetime`
  - `to_datetime`
  - `page`
  - `page_size`
- Returns organization-scoped appointments with pagination.

### POST /appointments

- Permission: `appointments.create`.
- Body: patient ID, clinician/department details, start/end times, appointment type.
- Verifies patient organization and schedule conflicts.
- Writes an appointment-created audit event.

### PATCH /appointments/{appointment_id}/status

- Permission: `appointments.update` or `appointments.cancel`.
- Body: new status.
- Enforces valid status transitions.
- Cancelled appointments cannot be silently reopened.

### PATCH /appointments/{appointment_id}

- Permission: `appointments.update`.
- Body: rescheduling fields and allowed appointment updates.
- Rechecks conflicts and tenant ownership.
- Writes a rescheduling audit event.

## 6. Encounters, Recordings, Transcripts, and Clinical Notes

### POST /encounters

- Permission: `encounters.create`.
- Body: selected patient and encounter metadata.
- The backend establishes patient, organization, and clinician linkage.
- Response: active encounter.

### GET /encounters/{encounter_id}

- Permission: `encounters.view`.
- Returns encounter only if it belongs to the current organization and permitted patient relationship.

### POST /encounters/{encounter_id}/recordings

- Permission: `recordings.create`.
- Body: filename, content type, base64 recording content.
- Validates active encounter, patient linkage, type, and size.
- Stores audio privately.
- Creates a transcript record and preserves encounter linkage.

### GET /transcripts/{transcript_id}

- Permission: `transcripts.view`.
- Returns status, provider, language, confidence, transcript text, and error state.

### POST /recordings/{audio_id}/transcribe

- Permission: `transcripts.create`.
- Creates a durable transcription job.
- Returns `202` and `QUEUED`; it does not hold the request open for provider processing.

### PATCH /transcripts/{transcript_id}/review

- Permission: `transcripts.update`.
- Body: reviewed transcript text and optional review metadata.
- Creates an immutable transcript version.
- Does not overwrite the original provider history silently.

### POST /clinical-notes

- Permission: `clinical_notes.create`.
- Body: patient ID, optional encounter ID, body/sections, and draft metadata.
- Encounter must be active and belong to the same patient and organization when supplied.
- Creates a draft and initial version.

### PATCH /clinical-notes/{note_id}

- Permission: `clinical_notes.update`.
- Body: editable draft fields.
- Approved/signed notes cannot be edited.
- Creates a new immutable version.

### POST /clinical-notes/{note_id}/summary

- Permission: `clinical_notes.update`.
- Generates an AI draft through the configured provider boundary.
- Production refuses unconfigured/sandbox providers.
- AI output remains draft and is audited.

### POST /clinical-notes/{note_id}/sign

- Permission: `clinical_notes.approve`.
- Signs/approves a note.
- Creates an approved immutable version.
- Writes an approval audit event.

### POST /clinical-notes/{note_id}/approve

- Permission: `clinical_notes.approve`.
- Alias/workflow endpoint for doctor approval.
- Same approval and immutability rules as sign.

### GET /clinical-notes/{note_id}/versions

- Permission: `clinical_notes.view`.
- Returns ordered immutable versions for a same-organization note.

### POST /clinical-notes/{note_id}/document

- Permission: `documents.create`.
- Only signed/approved notes may generate a PDF.
- Creates a private patient document linked to the note and encounter.
- Writes a document-generated audit event.

## 7. AI, Documents, Messages, Tasks, and Care Plans

### POST /assistant/query

- Permission: clinical/approved patient read policy.
- Body: patient ID and question.
- Current provider boundary may return a sandbox response in development.
- Production requires grounded provider, source allowlists, prompt-injection defense, and clinician review.

### POST /patients/{patient_id}/documents

- Permission: `documents.create`.
- Body: filename, content type, optional base64 content, review metadata.
- Validates upload type and size.
- Stores private document metadata and object reference.
- OCR is currently a provider boundary; production OCR requires a real safe parser/scanner.

### PATCH /patients/{patient_id}/documents/{document_id}/review

- Permission: `documents.create` or document-review policy.
- Query/body status: `pending`, `approved`, or `rejected`.
- Requires matching patient, document, and organization.
- Writes a document review audit event.

### GET /patients/{patient_id}/documents/{document_id}/download

- Permission: `documents.download`.
- Verifies patient, document, organization, storage key, and access policy.
- Reads from private storage and writes a download audit event.

### GET /messages

- Permission: messages policy.
- Returns organization-scoped staff/patient messages permitted for the caller.

### POST /messages

- Permission: message-send policy.
- Body: patient ID, subject, body, direction/recipient metadata.
- Server derives organization and validates patient relationship.
- Writes a message audit event.

### PATCH /messages/{message_id}/read

- Permission: message-read policy.
- Marks a permitted message as read.

### GET /tasks

- Permission: task-view policy.
- Returns organization-scoped tasks.

### POST /tasks

- Permission: task-create policy.
- Body: task title, description, assignee, due date, patient/encounter relation where applicable.
- Writes a task audit event.

### GET /care-plans

- Permission: care-plan-view policy.
- Returns organization-scoped care plans.

### POST /care-plans

- Permission: care-plan-create policy.
- Body: patient, goals, interventions, dates, and status.
- Must verify patient and organization relationship.

## 8. Patient Portal Endpoints

### GET /portal/patients/{patient_id}

- Permission: staff portal/clinical policy.
- Returns a staff-authorized patient portal view.
- Must not be confused with the self-scoped patient portal token flow.

### POST /patient-portal/register

- Authentication: controlled portal-account flow.
- Creates or activates a patient portal account for the intended patient relationship.
- Must not permit arbitrary patient impersonation.

### POST /patient-portal/login

- Authentication: public portal login.
- Body: patient portal credentials.
- Returns a portal token scoped to one patient and organization.

### GET /patient-portal/me

- Authentication: patient portal token.
- Returns the current portal account/patient identity.

### GET /patient-portal/overview

- Authentication: patient portal token.
- Returns only the authenticated patient's profile, appointments, messages, visits/documents permitted by policy.
- Ignores any client-supplied patient ID.

### POST /patient-portal/messages

- Authentication: patient portal token.
- Body: subject and message body.
- Server derives patient and organization from the portal account.
- Writes a message audit event.

### POST /patient-portal/documents

- Authentication: patient portal token and policy.
- Body: allowed document upload data.
- Must apply type/size validation and malware scanning before production use.

### GET /patient-portal/documents/{document_id}/download

- Authentication: patient portal token.
- Only approved documents belonging to the authenticated patient are downloadable.
- No public storage URL is returned as the security authority.

## 9. Job and Worker Behavior

### Email job flow

1. Password reset or invitation endpoint creates `EmailDeliveryJob`.
2. Job is stored with status, retry count, and availability time.
3. `python -m app.worker` claims due jobs.
4. SMTP provider sends the email.
5. Success marks job completed.
6. Failure retries with backoff until the configured limit.
7. Terminal failures remain explicit and observable.

### Transcription job flow

1. Recording endpoint creates `AudioFile` and `Transcript`.
2. Transcription endpoint creates `TranscriptionJob`.
3. API returns `202 QUEUED`.
4. Worker reads private audio.
5. Provider returns transcript or explicit error.
6. Job and transcript are updated to `COMPLETED`, `RETRY`, or `FAILED`.
7. No fake transcript is generated when the provider is unavailable.

## 10. What Each Client Must Connect

| Client feature | Endpoint(s) | Required backend/provider |
|---|---|---|
| Login | `/auth/login` | JWT/session database, optional MFA |
| Registration | `/auth/register` | Organization/user/RBAC provisioning |
| Invite staff | `/team/invites`, `/auth/invitations/accept` | Email worker and role catalog |
| Patient search | `/patients` | Tenant-scoped DB query and pagination |
| Start encounter | `/encounters` | Patient relationship and clinician permission |
| Recording | `/encounters/{id}/recordings` | Private storage and browser microphone |
| Transcription | `/recordings/{id}/transcribe`, `/transcripts/{id}` | Worker and STT provider |
| Note draft | `/clinical-notes`, `/clinical-notes/{id}` | Clinical note/version database |
| AI draft | `/clinical-notes/{id}/summary` | Configured AI provider and safety policy |
| Approval | `/clinical-notes/{id}/approve` | Approval permission and audit trail |
| PDF | `/clinical-notes/{id}/document` | ReportLab plus private storage |
| Patient download | Portal/document download routes | Portal token, approved document, storage |
| Audit | `/audit-events` | Append-only audit storage and retention job |

## 11. Endpoint Gaps Before Production

The current API is connected locally, but these integrations are still required before production PHI use:

1. PostgreSQL clean migration and deployment validation.
2. Redis-backed distributed rate limiting.
3. ClamAV or managed malware scanning before persistence.
4. Real BelMasry/Arabic STT credentials and contract tests.
5. Real AI provider credentials and clinical safety review.
6. Verified SMTP delivery, bounce handling, and monitoring.
7. Private S3/object storage with signed URL policy if filesystem storage is not used.
8. Real hospital OIDC and SAML IdP tests.
9. Full IDOR testing for every resource endpoint.
10. Accessibility and all-viewport browser QA.
11. SAST, DAST, dependency, container, and penetration testing.
12. Backup, restore, retention, incident response, and disaster recovery validation.
