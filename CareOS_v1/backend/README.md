# CareOS API

## Local setup

```powershell
Copy-Item .env.example .env
$env:POSTGRES_PASSWORD = "local-only-change-me"
docker compose up -d postgres
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API health check is available at `http://localhost:8000/api/v1/health`. Interactive docs are enabled only outside production.

Apply the identity and audit schema before running the API:

```powershell
alembic upgrade head
```

The service exposes database-backed registration, login, organization onboarding, team invites, and administrator audit events. Registration creates an empty organization; patients must be created through the protected API. No demo account or synthetic patient records are seeded automatically. Production still requires hospital OIDC/SAML, refresh-token rotation, email delivery for invites, and managed secrets. MFA uses encrypted TOTP secrets and one-time recovery codes.

Migrations `0005_rbac_entities` through `0008_profiles_and_sso_configuration` add organization-scoped roles/permissions, clinical workflow entities, secure recovery/MFA-ready fields, patient profiles, and tenant-owned SSO configuration. Protected role dependencies consult organization role assignments, and permission dependencies use assigned `RolePermission` rows.

Clinical endpoints now preserve the server-side chain `Patient -> Encounter -> AudioFile -> Transcript`. Speech-to-text uses a configurable backend provider and returns an explicit unavailable/not-configured error instead of fabricated text. Reset/invitation messages use SMTP with configurable retry/backoff. Permission evaluation is assignment-backed; the legacy role permission fallback is removed. The current migration head is `0013_mfa_recovery_codes`.

### OpenAI speech-to-text

Set `SPEECH_TO_TEXT_PROVIDER=openai`, `SPEECH_TO_TEXT_API_KEY`, and optionally `SPEECH_TO_TEXT_MODEL` in `backend/.env` (the default model is `gpt-4o-mini-transcribe`). The API URL defaults to OpenAI's audio-transcriptions endpoint; set `SPEECH_TO_TEXT_API_URL` only when using a compatible endpoint. The recording worker sends audio and the base language code, for example `ar` from `ar-EG`. Keep the key server-side, then restart both the API and `python -m app.worker` so they load the updated settings.

### Public landing assistant

The public Chat and Voice controls use `/api/v1/assistant/guest-chat` and `/api/v1/assistant/guest-voice`. For OpenAI-backed replies and speech transcription, set `AI_PROVIDER=openai`, `AI_MODEL=gpt-4o-mini`, and `AI_API_KEY` in `backend/.env`; the same key is used for transcription when `SPEECH_TO_TEXT_PROVIDER` is left `unconfigured`. Alternatively, configure a separate `SPEECH_TO_TEXT_PROVIDER` and `SPEECH_TO_TEXT_API_KEY`. Never put provider keys in frontend environment variables. Without credentials, development mode returns the labeled sandbox reply and voice requests report that provider configuration is unavailable.

Migration `0009_email_jobs_and_soft_delete` adds queued email jobs and soft-delete timestamps. Run `python -m app.worker` as a separate worker process to deliver queued reset/invitation email jobs. SAML production integration is available through `HospitalSAMLProvider` and requires the `python3-saml` dependency plus signed IdP metadata.

## Storage and identity hardening

Portal documents are written through `StorageService` using either local private filesystem storage or private S3. Documents are addressed by tenant-scoped keys and served through `GET /api/v1/patient-portal/documents/{document_id}/download`, which rechecks the portal account, patient, and organization before reading the object.

For external identity, configure `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `SSO_ALLOWED_REDIRECT_HOSTS`. The current adapter is OIDC-ready and development-compatible; production must add provider-library signature, issuer, audience, nonce, state, expiry, and verified-claim validation before enabling real sign-in.
