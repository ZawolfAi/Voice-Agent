# Security Notes

## Current MVP status

The repository now contains a FastAPI/PostgreSQL identity, organization, session, notification, invitation, and append-only audit foundation. The browser clinical modules still use synthetic demo records and must not receive real patient information until the server-side clinical API is complete.

The development-only browser fallback is enabled only when `import.meta.env.DEV` is true. Production builds require the API for authentication. Never use the fallback with real data.

## Tenant and document boundaries

- Every staff request resolves the user from the server-side session and scopes clinical records by `organization_id` before applying department/project rules.
- Patient-portal tokens carry tenant and patient claims, but the API also compares those claims with the persisted account and patient records on every request.
- Portal documents are stored under an organization/patient-prefixed key. The client receives an authenticated API download URL, never a public S3 object URL.
- Storage keys are validated on write, read, and delete. Path traversal, absolute paths, and backslash-based keys are rejected.
- S3 buckets must remain private. Use IAM roles or workload identity in production; do not expose access keys to the browser or `VITE_*` variables.

## External identity boundary

- SSO redirect targets are allowlisted by `SSO_ALLOWED_REDIRECT_HOSTS`; arbitrary callback hosts are rejected.
- Production OIDC must validate issuer, audience, signature, nonce, state, token expiry, and verified email/domain claims using a maintained provider library.
- Role and organization claims must be mapped through an explicit allowlist. Never trust a browser-supplied role or organization identifier.

## Release gate before real data

1. Replace synthetic clinical modules with authenticated, organization-scoped server APIs.
2. Configure hospital identity through `OIDC_*` or `SAML_METADATA_URL`, MFA, and verified role claims.
3. Enforce least-privilege RBAC on every clinical read, write, export, and AI action.
4. Use a managed secrets vault; set `SECRET_KEY` outside source control and rotate it.
5. Run the Alembic audit trigger migration; keep audit events append-only and include access/export/AI actions.
6. Configure `AUDIT_RETENTION_DAYS`, encrypted backups, `BACKUP_BUCKET`, restore drills, and deletion workflows.
7. Keep PHI out of browser bundles, request logs, exceptions, analytics, and error telemetry.
8. Isolate OCR/document parsing and add file validation, malware scanning, and sandboxing.
9. Add RAG source allowlists, prompt-injection defenses, grounded-answer checks, and clinician approval gates.
10. Run dependency, SAST, DAST, secret, container, backend, and Playwright scans in CI.
11. Complete privacy impact assessment, threat model, penetration test, incident response, and disaster recovery review.
