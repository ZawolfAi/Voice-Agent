# CareOS Platform & AI Voice Agent Integration Guide

This guide describes how the **AI Voice Agent & Multi-Agent Reception System** is connected with the **CareOS Platform** (`https://github.com/Ezatnasef/careos`), replacing CareOS's sandbox/mock AI services with the specialized Cosmetics & Aesthetic Dermatology agent.

---

## 1. Architecture Overview

```
                      +---------------------------------------+
                      |            CareOS Platform            |
                      |  - Landing Page Guest Chat & Voice    |
                      |  - Staff Global Chat Widget           |
                      |  - Clinical Note SOAP Drafting        |
                      |  - Appointments & Encounters DB       |
                      +-------------------+-------------------+
                                          |
                        HTTP POST /v1/voice/turns (Port 8765)
                        CareOS backend -> Voice Agent daemon
                                          |
                                          v
                      +---------------------------------------+
                      |    Voice Agent & Multi-Agent System   |
                      |  - Cosmetics Clinic Domain Expertise  |
                      |  - 100% Strict Language Mirroring:    |
                      |      * English -> English             |
                      |      * Arabic -> Egyptian Dialect     |
                      |  - No hardcoded opening/closing hours |
                      |  - Hidden internal model names/CoT    |
                      +-------------------+-------------------+
                                          |
                        HTTP REST API calls (Port 8000)
                        CareOSContract -> CareOS Backend
                        (POST /appointments, GET, PATCH)
                                          |
                                          v
                      +---------------------------------------+
                      |        CareOS Database (SQLite/PG)     |
                      |  - appointments table                 |
                      |  - conflict detection (HTTP 409)      |
                      +---------------------------------------+
```

---

## 2. Changes Made to CareOS (`backend/`)

CareOS designates `backend/app/integrations.py` as the official provider boundary (see `HANDOFF.md`). The following enhancements were implemented:

### A. `backend/app/config.py` & `.env.example`
- Added `voice_agent_url: str = "http://127.0.0.1:8765"`
- Added `voice_agent_api_key: str = ""`
- Configured default `ai_provider: str = "voice_agent"`

### B. `backend/app/integrations.py`
- Implemented `VoiceAgentProvider`:
  - `answer_general(message)`: Routes landing page guest chat, guest voice transcripts, and staff chat to the Voice Agent at `POST /v1/voice/turns`.
  - `answer(question)`: Handles doctor/staff clinical queries.
  - `summarize_note(note)`: Generates structured clinical SOAP drafts (Subjective, Objective, Assessment, Plan) with cosmetic procedure parameters (toxin units, filler volume, laser settings, and follow-ups).
- Implemented `VoiceAgentSpeechToTextProvider`:
  - Plugs into `get_speech_to_text_provider()` to handle Egyptian Arabic (`ar-EG`) and English (`en-US`) audio recordings.

### C. `backend/app/api.py`
- Enhanced `AppointmentInput` with alias normalization so both CareOS fields (`starts_at`, `reason`) and agent contract fields (`start_time`, `department`, `appointment_type`) are seamlessly accepted.
- Updated `update_appointment_status` to accept cancellation status from either URL query parameter (`?status=cancelled`) or JSON payload (`{"status": "cancelled"}`).

---

## 3. Changes Made to Voice Agent (`voice_agent/`)

### A. `voice_agent/app/orchestration/booking_contract.py`
- Enhanced `CareOSContract`:
  - Formats appointment creation requests with CareOS database fields: `starts_at`, `reason`, `status="confirmed"`, and `patient_id`.
  - Normalizes string patient identifiers into valid RFC-4122 UUIDs.
  - Parses CareOS appointment responses (`starts_at`, `reason`, `id`, `patient_id`).
  - Added `authenticate_with_careos` classmethod to automatically authenticate with CareOS demo login (`/auth/demo-login`) and obtain bearer tokens.

### B. Drop-in Integration Package (`voice_agent/integrations/careos/`)
- `careos_agent_provider.py`: Standalone adapter class for CareOS backend.
- `careos_sync.py`: Synchronization client for CareOS appointments.
- `test_careos_platform_integration.py`: Automated tests verifying payload structures, response parsing, and resilience.

---

## 4. How to Run Locally

### Step 1: Start the Voice Agent
```powershell
cd "d:\M.Tarek\ZAWOLF.AI\AI Agents\Voice Agent"
.\.venv\Scripts\python.exe -m voice_agent.app.main
```
The Voice Agent listens on: `http://127.0.0.1:8765`.

### Step 2: Start the CareOS Backend
In the CareOS repository root:
```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Step 3: Start the CareOS Frontend
```powershell
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 5. Verification Checklist

1. **Guest Chat / Voice Assistant**:
   - Open CareOS landing page at `http://localhost:5173`.
   - Ask in English: *"What cosmetic services do you offer?"* $\rightarrow$ The agent answers in English describing Botox, fillers, laser, and skin treatments.
   - Ask in Arabic: *"عاوزة أعرف أسعار جلسات الفيلر"* $\rightarrow$ The agent answers in friendly Egyptian Arabic.
2. **Appointment Scheduling**:
   - Say: *"عاوزة أحجز جلسة بوتوكس بكرة الساعة 3 العصر"*.
   - The agent books the appointment via `CareOSContract` directly into CareOS's `appointments` table.
   - If another patient asks for the exact same slot, CareOS detects the conflict (HTTP 409) and the agent offers alternative slots.
3. **Clinical Note Summaries**:
   - In CareOS Doctor Portal, click "Generate Summary" on any clinical note.
   - The note is processed into a professional SOAP summary.
