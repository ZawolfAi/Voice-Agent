# CareOS Architecture Roadmap

This document is a responsibility-oriented roadmap for turning the current CareOS prototype into a real production architecture.

## 1. Auth Specialist

Responsibilities:
- Implement `POST /auth/login`, `POST /auth/register`, `GET /me`, and `POST /auth/logout` as real backend APIs.
- Validate and rotate JWT access tokens.
- Enforce session revocation and logout audit.
- Ensure the returned `AuthUser` payload includes:
  - `id`
  - `organization_id`
  - `workspace_id`
  - `email`
  - `full_name`
  - `role`
  - `onboarding_complete`

## 2. SSO / Identity Provider Specialist

Responsibilities:
- Connect Hospital SSO to a real OIDC/SAML provider such as Azure Entra ID, Okta, Keycloak, or an internal IdP.
- Implement `POST /auth/sso/start` and `POST /auth/sso/callback` properly.
- Manage `state`, `nonce`, and `redirect_uri` safely.
- Normalize provider claims into:
  - `email`
  - `full_name`
  - `organization_domain`
  - `role`
  - `provider_user_id`
- Map claims to an existing organization/workspace or create a pending invite/onboarding request.

## 3. Organization / Workspace Specialist

Responsibilities:
- Implement `GET /organization`, `GET /workspace`, and `POST /workspace`.
- Create `Organization` records and `Workspace` records from onboarding.
- Link users to the correct organization and workspace.
- Resolve the route:
  - if `workspace` exists and `onboarding_complete = true` → `Dashboard`
  - otherwise → `Onboarding`

## 4. RBAC / Security Specialist

Responsibilities:
- Define a role-permission matrix for:
  - `physician`
  - `nurse`
  - `care_coordinator`
  - `administrator`
- Protect all clinical routes through `current_user` and `require_roles` successfully.
- Enforce `organization_id`, `workspace_id`, and `patient_id` scope checks.
- Add audit records for user sign-in, sign-out, patient access, note signing, onboarding changes, and team member invites.

## 5. Data / Clinical Data Specialist

Responsibilities:
- Replace demo-only dashboard data with real backend queries:
  - `GET /dashboard`
  - `GET /patients`
  - `GET /appointments`
  - `GET /team`
  - `GET /audit-events`
- Enforce `organization_id` scoping across all patient/clinical records.
- Return `kpi` and clinical metrics instead of only static synthetic examples.
- Store patient privacy and audit fields correctly.

## 6. Integration Specialist

Responsibilities:
- Connect `Clinical Assistant`, `RAG`, `OCR`, and `EHR` adapters to production providers.
- Add providers behind a `backend/app/integrations.py` implementation path.
- Provide `confidence`, `source`, `document`, and `human review` chains for clinical note summaries.
- Connect email/SMS notifications and team invite delivery to the real notification provider.

## 7. Frontend Specialist

Responsibilities:
- Keep route selection consistent with backend auth outcome:
  - `dashboard` if `onboarding_complete = true` and workspace exists
  - `onboarding` if onboarding is still incomplete
- Replace all static `src/data.ts` fallback reads with real API-backed project data.
- Connect the `Hospital SSO` start and callback flow to the actual backend contract.
- Ensure the UI remains bilingual and accessible across the full route tree.

## End-to-End Product Flow

1. User selects `Email / Password` or `Hospital SSO`.
2. Backend authenticates the user or returns SSO redirect.
3. Backend returns `AuthUser` with `organization_id`, `workspace_id`, `role`, and `onboarding_complete`.
4. Frontend routes the user:
   - Dashboard if `workspace` exists and `onboarding_complete = true`
   - Onboarding if not complete or workspace missing
5. Dashboard pulls live clinical data tied to organization/workspace scope.
6. Integration services provide AI, RAG, OCR, EHR, and notification behavior.

## Implementation Priority

Phase 1: Auth and user payload contract.
Phase 2: Organization and workspace creation.
Phase 3: RBAC and organization-scoped data access.
Phase 4: Dashboard and clinical data APIs.
Phase 5: Hospital SSO callback and identity mapping.
Phase 6: LLM/RAG/OCR/EHR/Notification integration.
Phase 7: Full end-to-end route validation and production readiness.
 ------------------------------------------
 SSO فعلي

لازم نضيف real OIDC/SAML adapter داخل sso.py.
لازم نربط login route من واجهة الدخول في api.ts بـ callback و token validation.
لازم نحدد mapping صحيح بين email/domain و organization و role.
Organization / Workspace real lifecycle

في workspace.py لازم نكتب create/update/get workspace فعلي.
يحتاج organization_id, workspace_id, department, timezone, onboarding_complete فعلاً.
لازم ربطه بالـ user في models.py و auth.py.
RBAC فعلي

في rbac.py لازم نضيف permissions كاملة لكل role، وليس مجرد matrix placeholder.
لازم تطبق permissions على patients, appointments, team, audit, dashboard, notes.
لازم نمنع الوصول عبر current_user و require_roles.
API contract فعلي

في api.py نحتاج endpoints أوسع:
auth login/register/me/logout
sso start/callback
organization get/update
workspace get/create
dashboard real data
في api.ts لازم تكتمل الواجهة مع جميع هذه الـ routes.
Dashboard real data

موجود في api.py dashboard مفروض يرجع KPI + appointments + followups + patients.
لازم نضيف real kpi, team, alerts, clinical metrics, RBAC scoped data.
لا يفضل أن dashboard يفتح من data.ts فقط.
Integration layer

الــ LLM / RAG / OCR / Documentation / EHR / Notifications لازم يكوّنوا Integration Specialist flow في integrations.py.
لازم نحدد provider لكل خدمة فعليًا ونسجل source + confidence + human review.
Product flow end-to-end

Login
SSO or Email
GET /me
Check organization/workspace
Onboarding if onboarding_complete = false
Dashboard if workspace exists and user authorized
يعني بصياغة بسيطة جدًا:

واجهة موجودة
Auth موجود
Organization/Workspace skeleton موجود
SSO skeleton موجود
RBAC skeleton موجود
Contract layer موجود
لكن ما زال ناقص التنفيذ الحقيقي للـ identity provider، database mapping، permissions enforcement، dashboard real data، و integration providers.
الخلاصة:

المشروع الآن “قابل للتمديد” و“مرتب كـ architecture”.
لكنه ما زال “مش كامل” ولا يحق تسمية النظام حقيقي 100% إلا بعد تنفيذ الـ SSO، Workspace creation، RBAC، Dashboard real data، و Integration provider.