# CareOS handoff guide

## Verified local status

This project is now verified in a working local development state.

The following checks were completed successfully in the current session:

- FastAPI backend started successfully after clearing the stale process on port 8000
- `GET http://127.0.0.1:8000/api/v1/health` returned `{"status":"ok"}`
- `POST /api/v1/auth/demo-login` returned a valid access token and user payload
- `npm run build` completed successfully
- Playwright route test for the account/profile page passed: `1 passed (13.9s)`

This means the application is currently stable enough for local development and live feature validation, but it is not yet a production PHI-ready deployment.

## What runs today

The project currently runs as:

- Vite + React frontend on the local browser app
- FastAPI backend serving API routes on `127.0.0.1:8000`
- SQLite local database used for development verification
- Local auth/session flow with working demo login and token restoration

This is a functioning local runtime baseline, not a final production deployment.

## Runtime flow

```text
React app -> /api/v1 -> FastAPI -> SQLite local DB
                     -> auth/session validation
                     -> feature APIs (dashboard, patients, appointments, notes, docs, portal)
```

The frontend is connected to the API layer and can validate real route access and auth state. The project is now in a working local state, which is the correct foundation before full production hardening.

## Current verified working areas

- Backend startup and app boot
- Health endpoint
- Demo auth flow
- Access token generation and user payload
- Frontend build
- Profile/account route navigation
- Session-oriented app shell behavior
- Core functional UI shell and route flow

## Current status by area

### Ready / verified

- backend startup
- health endpoint
- demo login
- session restore path
- build pipeline
- account page navigation
- role-aware front-end shell

### Still requiring hardening or real production setup

- production-grade database deployment
- production secrets and environment configuration
- full RBAC validation across all routes and features
- end-to-end verification of every feature page with real data
- SSO provider cert/JWKS and callback hardening
- object storage and document pipeline scale validation
- background workers and notification delivery
- real PHI deployment controls and release checks

## Provider replacement points

`backend/app/integrations.py` remains the correct place to isolate vendor implementations behind backend interfaces.

Keep provider code server-side only.

- `ClinicalSummaryProvider.summarize`: approved LLM backend
- `RagProvider.answer`: retrieval backend with citations and policy controls
- `OcrProvider.extract`: OCR implementation only on the backend
- `NotificationProvider.queue`: email, SMS, or messaging system integration

Do not call provider logic from React and do not expose credentials to the browser.

## Operational expectations

- The app must not be treated as production-ready until the security gates in `SECURITY.md` are met.
- Local development is valid for feature verification and route validation.
- Demo user flows are okay for local testing, but real launch must use controlled environment configuration and production-safe DB/storage setup.

## Required next work

1. Validate every feature page against real API data instead of just demo flow.
2. Complete a full RBAC/access review for every protected route.
3. Harden SSO callback and provider verification.
4. Move from SQLite local verification to a production-safe storage strategy.
5. Finish security and deployment gates before any PHI or production exposure.
6. Keep a clean startup process by preventing stale API processes from reusing port 8000.

## Useful local command pattern

Run the backend locally with the correct development environment:

```powershell
Set-Location 'F:\all work\careos-main\backend'
$env:APP_ENV='development'
$env:DATABASE_URL='sqlite+aiosqlite:///./careos-local.db'
& 'C:\Users\Nasef\anaconda3\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then verify:

```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/v1/health' -Method GET
```

And build the frontend:

```powershell
Set-Location 'F:\all work\careos-main'
npm run build
```

## Final summary

The project is now in a valid local working state, with the critical startup/auth/build problems resolved and verified. The next phase is not “rewrite from scratch”; it is focused hardening, production configuration, and broader feature validation before any production release.
