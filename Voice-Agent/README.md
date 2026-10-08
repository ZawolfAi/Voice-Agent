# 🎙️ Healthcare & Cosmetics AI Voice Agent Backend

An enterprise-ready **AI Voice Agent & Multi-Agent Reception Backend** designed for healthcare, aesthetic dermatology, and cosmetics clinics. This service provides real-time natural language conversational scheduling, 100% strict language mirroring (English & Egyptian Arabic), and direct integration contracts for clinic management platforms.

---

## 🌟 Key Features

- **Strict Language Mirroring**:
  - **English User Utterances** $\rightarrow$ Responds strictly in professional, natural conversational English.
  - **Arabic User Utterances** $\rightarrow$ Responds strictly in friendly Egyptian Arabic (اللهجة المصرية) written in Arabic script.
  - Zero cross-language bleed.
- **Domain Specialization**: Specialized in cosmetic procedures (Botox, dermal fillers, laser sessions, hydrafacials, skin rejuvenation). Polite redirection for out-of-scope departments.
- **No Hallucinations**: Dynamically checks clinic availability and rules via backend API contracts. Never invents doctor names, prices, or appointment slots.
- **Real-Time Voice & Text Support**:
  - **Single-turn REST API** (`POST /v1/voice/turns`) for chat widgets and transcribed audio.
  - **Server-Sent Events (SSE)** (`POST /v1/voice/turns/stream`) for token-by-token streaming with internal thoughts separated from user replies.
  - **Bidirectional Live Voice WebSocket** (`WS /v1/voice/live`) powered by Google Gemini Live (`gemini-3.8-live`).
  - **Text-to-Speech (TTS)** (`POST /v1/voice/tts`) audio synthesis.
- **Pure Backend Architecture**: Ready for direct platform integration as a microservice daemon or mounted FastAPI sub-application. Frontend responsibilities remain with the host platform.

---

## 🏗️ System Architecture & Platform Integration

```text
                      ┌────────────────────────────────────────┐
                      │            Platform Host               │
                      │  - Landing Page Chat & Voice Widget    │
                      │  - Staff Portal & Encounters           │
                      │  - Appointments Database               │
                      └───────────────────┬────────────────────┘
                                          │
                         HTTP POST /v1/voice/turns (Port 8765)
                         WebSocket /v1/voice/live
                                          │
                                          ▼
                      ┌────────────────────────────────────────┐
                      │    Voice Agent Backend Daemon          │
                      │  - Domain Extraction & Slot Checking   │
                      │  - 100% Language Mirroring (en / ar-EG)│
                      │  - Pydantic State Management           │
                      └───────────────────┬────────────────────┘
                                          │
                         REST API Calls (CareOSContract)
                         POST /api/v1/appointments (Port 8000)
                                          │
                                          ▼
                      ┌────────────────────────────────────────┐
                      │        Platform REST Backend           │
                      │  - Appointments Table                  │
                      │  - Double-Booking Conflict (HTTP 409)  │
                      └────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```text
Voice Agent/
├── .env.example              # Environment variables template
├── .gitignore                # Comprehensive exclusions (never commits secrets or venvs)
├── pyproject.toml            # Pytest & package discovery configuration
├── requirements.txt          # Python dependencies
├── README.md                 # Project documentation & integration guide
├── simulate_careos_sync.py   # Runnable end-to-end simulation between Agent & CareOS
├── api-endpoints.md          # Reference CareOS platform API specification
└── voice_agent/
    ├── __init__.py
    ├── app/
    │   ├── agent/            # Agent state, slot extractors, and prompts
    │   │   ├── multilingual.py  # Language detection & strict Egyptian Arabic formatting
    │   │   ├── prompts.py       # System guidance & role instructions
    │   │   ├── state.py         # Conversation state schemas
    │   │   └── voice_agent.py   # Core VoiceAgent orchestrator
    │   ├── audio/            # TTS and speech synthesis handlers
    │   ├── llm/              # LLM client abstractions (Gemini, OpenAI, DemoProvider)
    │   ├── orchestration/    # HTTP client & booking contracts (CareOSContract)
    │   ├── schemas/          # Pydantic models (requests, auth, slots)
    │   ├── api.py            # FastAPI route handlers (/v1/voice/turns, /v1/voice/tts)
    │   ├── bootstrap.py      # Composition root for mounting onto host FastAPI apps
    │   ├── config.py         # Pydantic Settings configuration loader
    │   ├── live_voice.py     # Gemini Live bidirectional WebSocket bridge
    │   └── server.py         # Standalone daemon entrypoint (port 8765)
    ├── integrations/
    │   └── careos/           # Drop-in integration adapter for CareOS
    │       ├── README_CAREOS_INTEGRATION.md  # Detailed CareOS integration walkthrough
    │       ├── careos_agent_provider.py      # HTTP adapter client for CareOS backend
    │       ├── careos_sync.py                # Appointment synchronization client
    │       └── patches/                      # Ready-to-copy patch files for CareOS repo
    └── tests/                # 80 automated unit & integration tests
```

---

## 🔌 Integration Guide for the Platform Team

There are two primary ways to integrate this agent with your platform:

### Method 1: Standalone Microservice Daemon (Recommended)

1. Start the Voice Agent daemon on port `8765`:
   ```bash
   python -m voice_agent.app.server
   ```
2. In your platform backend (e.g. CareOS `backend/app/integrations.py`), use the pre-built adapter:
   ```python
   from voice_agent.integrations.careos.careos_agent_provider import CareOSVoiceAgentAdapter

   agent = CareOSVoiceAgentAdapter(base_url="http://127.0.0.1:8765")

   # Forward user text / transcript
   result = await agent.answer_general("عاوزة أحجز جلسة بوتوکس بكرة الساعة 3 العصر")
   print(result["answer"])  # Returns confirmed booking or conflict in Egyptian Arabic
   ```
3. In your platform frontend, connect your live voice widget to:
   ```text
   ws://127.0.0.1:8765/v1/voice/live
   ```

### Method 2: Embedded FastAPI Sub-Application

If you prefer to run everything in a single process, mount the Voice Agent API directly onto your existing FastAPI application:

```python
from fastapi import FastAPI
from voice_agent.app.bootstrap import create_voice_api
from voice_agent.app.config import Settings
from voice_agent.app.orchestration.booking_contract import CareOSContract

app = FastAPI()

voice_settings = Settings(
    app_env="development",
    orchestrator_mode="staging",
    orchestrator_url="http://localhost:8000/api/v1",
)

voice_sub_app = create_voice_api(
    settings=voice_settings,
    authenticator=your_auth_provider,
    conversation_store=your_conversation_store,
    orchestrator_contract=CareOSContract(token="jwt-token", department="Cosmetics"),
)

# Mount as sub-application
app.mount("/voice-service", voice_sub_app)
```

### Method 3: Pre-Built Patches for CareOS

If integrating into the [CareOS Platform](https://github.com/Ezatnasef/careos), check `voice_agent/integrations/careos/patches/`:
- `patches/app/integrations.py`: Pre-configured provider replacement.
- `patches/app/config.py`: Environment variable definitions for `voice_agent_url`.
- `patches/app/api.py`: Updated appointment models supporting normalized booking fields.

---

## 📡 API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Service information, version, and endpoints map |
| `GET` | `/health` | Health & liveness check |
| `GET` | `/status` | Runtime provider & live voice readiness status |
| `POST` | `/v1/voice/turns` | Single-turn JSON conversation & booking turn |
| `POST` | `/v1/voice/turns/stream` | Server-Sent Events (SSE) token-by-token streaming |
| `POST` | `/v1/voice/tts` | Text-to-speech audio synthesis |
| `WS` | `/v1/voice/live` | Bidirectional real-time Gemini Live WebSocket |
| `WS` | `/v1/voice/transcribe` | Real-time speech-to-text WebSocket |

### Example: POST `/v1/voice/turns`

**Request:**
```json
{
  "text": "محتاج أحجز جلسة ليزر بكرة الساعة 6 مساء",
  "session_id": null
}
```

**Response:**
```json
{
  "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "response_text": "تم تأكيد حجز موعدك بنجاح في عيادة التجميل. كود الحجز: careos-apt-4001.",
  "intent": "BOOK_APPOINTMENT"
}
```

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11, 3.12, 3.13)
- Gemini API key from [Google AI Studio](https://aistudio.google.com/) (for live voice and multilingual translation)

### 2. Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd "Voice Agent"

# Create and activate virtual environment
python -m venv .venv

# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

```bash
cp .env.example .env
```
Edit `.env` to set your credentials:
```env
LLM_PROVIDER=gemini
LLM_API_KEY=your_gemini_api_key_here
ORCHESTRATOR_MODE=mock   # Change to 'staging' when connecting to live CareOS backend
```

### 4. Running the Backend Server

```bash
python -m voice_agent.app.server
```
The server will start at: `http://127.0.0.1:8765`.
Interactive OpenAPI docs are available at: `http://127.0.0.1:8765/docs`.

### 5. Running the CareOS Sync Simulation

Verify the full multi-agent synchronization and booking conflict handling:
```bash
python simulate_careos_sync.py
```

### 6. Running Tests

Run the full automated test suite (80 tests):
```bash
pytest
```

---

## 🔒 Security Best Practices

- **Never Commit Secrets**: `.env` is ignored by `.gitignore`. Keep your Google Gemini API keys private.
- **Production Storage**: For production deployments, replace `InMemoryConversationStore` with Redis or PostgreSQL session storage.
- **Authentication**: When mounting in production, supply your trusted `HostAuthenticator` implementation so patient identities are derived from validated JWT/session tokens, never from unauthenticated client payloads.
=======
# Voice-Agent
>>>>>>> bd6014d162bb3e239a0496cfa4d30cf290163ea4
