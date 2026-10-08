# CareOS API Reference

This reference documents the current production-oriented backend contract for CareOS.

Base URL:

```text
http://localhost:8000/api/v1
```

Authentication:

```http
Authorization: Bearer <access_token>
```

---

## 1. System endpoints

### GET /health
Returns service health.

Response example:

```json
{
  "status": "ok"
}
```

### GET /readiness
Checks DB readiness.

Response example:

```json
{
  "status": "ready"
}
```

### GET /metrics
Protected: requires authenticated clinical user.

Response example:

```json
{
  "app": "careos-api",
  "environment": "development",
  "deployment": "careos-local",
  "roles": ["administrator"],
  "patients": 18,
  "appointments": 25,
  "metrics_enabled": true,
  "sso_ready": false
}
```

### GET /system/status
Returns environment and deployment metadata.

### POST /system/audit/cleanup
Protected: administrator only.

Response example:

```json
{
  "deleted": 7,
  "retention_days": 2555
}
```

---

## 2. Authentication

### POST /auth/register
Creates a new organization and first admin user.

Request body:

```json
{
  "email": "admin@clinic.example",
  "password": "StrongPass123!",
  "full_name": "Dr. Sarah Ali",
  "organization_name": "NorthCare Health",
  "department": "General Medicine",
  "project": "Outpatient",
  "role": "administrator"
}
```

Response example:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "organization_id": "uuid",
    "department": "General Medicine",
    "project": "Outpatient",
    "email": "admin@clinic.example",
    "email_verified": false,
    "full_name": "Dr. Sarah Ali",
    "role": "admin",
    "permissions": ["dashboard", "patients", "analytics"],
    "onboarding_complete": false
  }
}
```

### POST /auth/login

Request:

```json
{
  "email": "admin@clinic.example",
  "password": "StrongPass123!"
}
```

### POST /auth/logout
Protected. Revokes the current session token.

### GET /me
Protected. Returns current user profile.

### POST /auth/verify-email
Protected.

Request:

```json
{
  "email": "admin@clinic.example"
}
```

### POST /auth/sso/start
Starts an external SSO flow.

Request:

```json
{
  "provider": "hospital_sso",
  "email": "dr.rana@citycare.org",
  "redirect_uri": "https://app.example.com/callback"
}
```

Response:

```json
{
  "provider": "hospital_sso",
  "redirect_url": "https://issuer.example.com?...",
  "state": "uuid",
  "nonce": "uuid"
}
```

### POST /auth/sso/callback
Completes the identity provider callback.

Request:

```json
{
  "provider": "hospital_sso",
  "code": "auth-code",
  "state": "uuid"
}
```

Response includes:

```json
{
  "provider": "hospital_sso",
  "status": "authenticated",
  "claims": {
    "email": "dr.rana@citycare.org",
    "role": "physician"
  },
  "mapped": {
    "organization_name": "Citycare Health",
    "organization_domain": "citycare.org"
  },
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "dr.rana@citycare.org",
    "role": "physician"
  }
}
```

### POST /auth/sso
Alternative identity login endpoint.

---

## 3. Organization and workspace

### GET /organization
Protected.

### GET /workspace
Protected.

### POST /workspace
Protected: administrator only.

Request:

```json
{
  "name": "CityCare Central Clinic",
  "department": "General Medicine",
  "timezone": "UTC"
}
```

### PATCH /organization
Protected: administrator only.

Request:

```json
{
  "name": "Updated Clinic Name",
  "department": "Cardiology",
  "timezone": "UTC"
}
```

---

## 4. Team and audit

### GET /team
Protected. Returns all users in the same organization.

### POST /team/invites
Protected: administrator only.

Request:

```json
{
  "email": "newdoctor@clinic.example",
  "role": "physician"
}
```

### GET /audit-events
Protected: administrator only.

### GET /notifications
Protected.

### PATCH /notifications/{notification_id}/read
Protected.

---

## 5. Clinical core

### GET /dashboard
Protected. Returns organization-scoped patient and appointment summary.

Response example:

```json
{
  "patient_count": 12,
  "upcoming_appointments": [
    {
      "id": "uuid",
      "patient_id": "uuid",
      "starts_at": "2026-09-14T09:00:00Z",
      "reason": "Follow-up review",
      "status": "pending",
      "reminder_status": "queued"
    }
  ],
  "followups": [
    {
      "id": "uuid",
      "medical_record_number": "MRN-1205",
      "given_name": "Mariam",
      "family_name": "Hassan",
      "care_status": "follow_up_due"
    }
  ]
}
```

### GET /patients
Protected.

Query params:

```text
q=search term (optional; name, MRN, or date of birth)
page=1-based page number (optional, default 1)
page_size=page size (optional, default 50, maximum 100)
```

Results are organization-scoped and filtered by the authenticated user's department/project policy. The endpoint returns only the requested page; it never trusts an organization identifier from the client.

### POST /patients
Protected: physician, nurse, care coordinator, or administrator.

Request:

```json
{
  "medical_record_number": "MRN-2041",
  "given_name": "Nadia",
  "family_name": "Youssef",
  "department": "Cardiology",
  "project": "Heart Clinic",
  "date_of_birth": "1992-09-13",
  "gender": "female",
  "condition": "Follow-up review",
  "care_status": "stable"
}
```

### GET /patients/{patient_id}
Protected.

### PATCH /patients/{patient_id}
Protected.

### GET /appointments
Protected.

Query params:

```text
status=pending|confirmed|arrived|cancelled (optional)
from_at=ISO timestamp (optional)
to_at=ISO timestamp (optional)
page=1-based page number (optional)
page_size=1..100 (optional)
```

### POST /appointments
Protected.

Request:

```json
{
  "patient_id": "uuid",
  "encounter_id": "uuid",
  "starts_at": "2026-09-20T09:00:00Z",
  "reason": "Medication review",
  "status": "pending"
}
```

### POST /encounters/{encounter_id}/recordings
Protected. Stores private audio linked server-side to the active encounter and creates a transcript record.

### GET /transcripts/{transcript_id}
Protected. Returns transcript status, language (`ar-EG` by default), confidence, and failure code when applicable.

### POST /recordings/{audio_id}/transcribe
Protected. Runs the configured server-side speech-to-text provider. When no provider is configured it returns `503` and marks the transcript `FAILED`; no fake text is generated.

### PATCH /appointments/{appointment_id}/status
Protected.

Query param:

```text
status=pending|confirmed|arrived|cancelled
```

Cancelled appointments cannot be reopened. New appointments must be scheduled in the future, and active appointments cannot share the same organization time slot.

### PATCH /appointments/{appointment_id}
Protected. Reschedules an active appointment or updates its reason. Rescheduling validates the future timestamp and rejects conflicts with other active appointments.

Request example:

```json
{
  "starts_at": "2026-09-22T10:30:00Z",
  "reason": "Medication review"
}
```

### POST /encounters
Protected. Creates an active encounter for an organization-scoped patient.

### GET /encounters/{encounter_id}
Protected. Returns the encounter only when the authenticated user can access its organization and patient scope.

### POST /clinical-notes
Protected: physician, nurse, or administrator.

Request:

```json
{
  "patient_id": "uuid",
  "body": "Patient reports improved sleep quality after medication adjustment.",
  "ai_draft": "Optional draft summary"
}
```

### POST /clinical-notes/{note_id}/summary
Protected.

### POST /clinical-notes/{note_id}/sign
Protected: physician or administrator.

### PATCH /clinical-notes/{note_id}
Protected. Updates a draft and creates an immutable `ClinicalNoteVersion`. Signed notes cannot be edited.

### GET /clinical-notes/{note_id}/versions
Protected. Returns the immutable note history.

### POST /clinical-notes/{note_id}/approve
Protected. Approves/signs the note and creates the approved immutable version.

### POST /clinical-notes/{note_id}/document
Protected. Generates a private PDF only after approval and attaches it to the patient and encounter.

### POST /assistant/query
Protected.

Request:

```json
{
  "patient_id": "uuid",
  "question": "What are the key follow-up concerns for this patient?"
}
```

### POST /patients/{patient_id}/documents
Protected.

Request:

```json
{
  "filename": "lab_report.pdf",
  "content": "base64-encoded-bytes",
  "content_type": "application/pdf"
}
```

The response includes OCR status and a tenant-scoped authenticated `download_url`.

### GET /patients/{patient_id}/documents/{document_id}/download
Protected. Requires the same organization and patient access checks as the upload route.

---

## 6. Messages and tasks

### GET /messages
Protected.

### POST /messages
Protected.

Request:

```json
{
  "patient_id": "uuid",
  "subject": "Medication check-in",
  "body": "Please confirm updated blood pressure schedule.",
  "sender_type": "care_team",
  "direction": "outbound"
}
```

### GET /tasks
Protected.

### POST /tasks
Protected.

Request:

```json
{
  "patient_id": "uuid",
  "title": "Review home BP log",
  "description": "Review last 7 days of blood pressure readings.",
  "assignee": "Dr. Rana Samir",
  "priority": "high",
  "status": "pending",
  "due_at": "2026-09-20T09:00:00Z"
}
```

### GET /care-plans
Protected.

### POST /care-plans
Protected.

Request:

```json
{
  "patient_id": "uuid",
  "title": "Cardiac rehab plan",
  "summary": "Monitor blood pressure and medication adherence.",
  "status": "active",
  "goals": [
    "Track blood pressure",
    "Review medication adherence"
  ]
}
```

---

## 7. Portal endpoints

### GET /portal/patients/{patient_id}
Protected: clinical staff user.

### POST /patient-portal/register
Public. Creates a portal account for a patient.

Request:

```json
{
  "patient_id": "uuid",
  "email": "patient@example.com",
  "password": "PortalPass123!",
  "full_name": "Mina Saleh"
}
```

### POST /patient-portal/login
Public. Returns patient portal access token.

Request:

```json
{
  "email": "patient@example.com",
  "password": "PortalPass123!"
}
```

Response:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "patient_id": "uuid",
    "email": "patient@example.com",
    "full_name": "Mina Saleh",
    "role": "patient"
  }
}
```

### GET /patient-portal/me
Protected: patient portal token.

### POST /patient-portal/documents
Protected: patient portal token.

Request:

```json
{
  "filename": "lab_report.pdf",
  "content": "Zm9v",
  "content_type": "application/pdf"
}
```

The content field is base64-encoded document bytes.

The response contains a `download_url` pointing back to the authenticated API. It is not a public S3 URL.

### GET /patient-portal/documents/{document_id}/download
Protected: patient portal token.

The document is returned only when the token's patient and organization match the persisted document ownership. S3 buckets and filesystem storage must remain private to the API process.

---

## 8. Analytics and reports

### GET /department-metrics
Protected.

### GET /analytics
Protected.

### GET /reports
Protected.

---

## 9. Data contracts and notes

Important application data objects currently used by the backend include:

- User
- Organization
- Patient
- Appointment
- ClinicalNote
- PatientDocument
- PatientPortalAccount
- PatientPortalDocument
- CarePlan
- Task
- AuditEvent

The backend enforces organization-scoped access for clinical records and uses role-based rules from the RBAC layer.

---

## 10. Security and production assumptions

This project is currently a real MVP foundation, not a full healthcare production deployment.

Important assumptions:

- JWT tokens are used for authentication and session validation.
- Argon2 is used for password hashing.
- Organization IDs and patient records are scoped by organization.
- Portal tokens validate patient and organization identity before allowing access.
- S3 is supported as a private document backend through the storage abstraction; configure `STORAGE_BACKEND=s3`, `S3_BUCKET`, and `S3_REGION`.
- Storage keys are organization/patient scoped and reject traversal or absolute path segments.
- SSO callback hosts are restricted by `SSO_ALLOWED_REDIRECT_HOSTS`; subdomains of an approved host are accepted.
- OIDC discovery is now implemented as a real provider adaptation point.
- Real production deployment still needs hardened secrets, TLS, MFA, refresh rotation, and external IdP configuration.

---

## 11. Local development

Frontend:

```powershell
npm install
npm run dev
```

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Docker-based stack:

```powershell
docker compose up --build
```

---

## 12. Common HTTP status codes

- 200 OK
- 201 Created
- 204 No Content
- 400 Bad Request
- 401 Unauthorized
- 403 Forbidden
- 404 Not Found
- 409 Conflict
- 422 Unprocessable Entity
- 500 Internal Server Error

---

## 13. Recommended next steps

1. Add refresh-token rotation and device/session tracking.
2. Enforce stricter tenant isolation across all uploads and patient records.
3. Connect real OIDC/SAML providers for hospital identity.
4. Replace sandbox AI/OCR providers with real service integrations.
5. Add pagination, audit export, and retention enforcement for clinical records.
6. Add end-to-end tests for the portal, SSO, and analytics flows.
