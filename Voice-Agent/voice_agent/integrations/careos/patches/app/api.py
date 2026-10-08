import base64
import binascii
import hashlib
import json
import secrets
import httpx
from time import monotonic
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import String, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from .config import get_settings
from .db import get_session
from .email_service import enqueue_email
from .sso import HospitalSSOAdapter, SSOClaims
from .storage import StorageService

from .auth import (
    AuditEventResponse,
    InviteRequest,
    LoginRequest,
    OrganizationUpdate,
    RegisterRequest,
    VerifyEmailRequest,
    _token_for,
    authenticate,
    current_user,
    password_hasher,
    permissions_for_user,
    encrypt_mfa_secret,
    decrypt_mfa_secret,
    generate_totp_secret,
    verify_totp,
    public_user,
    require_permission,
    provision_role_assignments,
    register_user,
    revoke_token,
    require_roles,
    write_audit,
)
from .rbac import ROLE_PERMISSIONS, can_access_patient_scope, can_access_section, normalize_role
from .integrations import get_speech_to_text_provider, ocr_provider, rag_provider, summary_provider
from .models import Appointment, AudioFile, AuditEvent, AuthSession, CarePlan, ClinicalNote, ClinicalNoteVersion, Encounter, Notification, Organization, Patient, PatientDocument, PatientMessage, PatientPortalAccount, PatientPortalDocument, PatientPortalSession, PasswordResetToken, PatientProfile, Permission, ReminderJob, Role, RolePermission, SSOConfiguration, Task, TeamInvite, Transcript, TranscriptVersion, TranscriptionJob, User, UserRole

router = APIRouter()
bearer = HTTPBearer(auto_error=False)
_guest_chat_windows: dict[str, tuple[float, int]] = {}
_GUEST_CHAT_LIMIT = 10
_GUEST_CHAT_WINDOW_SECONDS = 60
_GUEST_CHAT_MAX_CLIENTS = 4096


def _allow_guest_chat(client_ip: str) -> tuple[bool, int]:
    now = monotonic()
    window = _guest_chat_windows.get(client_ip)
    if window is None or now - window[0] >= _GUEST_CHAT_WINDOW_SECONDS:
        if window is None and len(_guest_chat_windows) >= _GUEST_CHAT_MAX_CLIENTS:
            expired_clients = [
                ip
                for ip, (started_at, _) in _guest_chat_windows.items()
                if now - started_at >= _GUEST_CHAT_WINDOW_SECONDS
            ]
            for ip in expired_clients:
                _guest_chat_windows.pop(ip, None)
            if len(_guest_chat_windows) >= _GUEST_CHAT_MAX_CLIENTS:
                return False, _GUEST_CHAT_WINDOW_SECONDS
        _guest_chat_windows[client_ip] = (now, 1)
        return True, 0
    if window[1] >= _GUEST_CHAT_LIMIT:
        return False, max(1, int(_GUEST_CHAT_WINDOW_SECONDS - (now - window[0])))
    _guest_chat_windows[client_ip] = (window[0], window[1] + 1)
    return True, 0


class PatientInput(BaseModel):
    medical_record_number: str = Field(min_length=2, max_length=64)
    given_name: str = Field(min_length=1, max_length=120)
    family_name: str = Field(min_length=1, max_length=120)
    department: str = Field(default="", min_length=0, max_length=120)
    project: str = Field(default="", min_length=0, max_length=120)
    date_of_birth: date
    gender: str = "unspecified"
    condition: str = ""
    care_status: str = "stable"


class PatientProfileInput(BaseModel):
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=500)
    emergency_contact: str | None = Field(default=None, max_length=240)


class AppointmentInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    patient_id: UUID
    starts_at: datetime
    reason: str = Field(min_length=2, max_length=240)
    status: str = "pending"

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: object) -> object:
        if isinstance(data, dict):
            # Map start_time -> starts_at if needed
            if "starts_at" not in data and "start_time" in data:
                data["starts_at"] = data["start_time"]
            # Map appointment_type / department -> reason if reason is missing
            if not data.get("reason"):
                appt_type = data.get("appointment_type")
                dept = data.get("department")
                if appt_type and dept:
                    data["reason"] = f"{dept} - {appt_type}"
                elif appt_type:
                    data["reason"] = str(appt_type)
                elif dept:
                    data["reason"] = str(dept)
                else:
                    data["reason"] = "Cosmetics Consultation"
        return data


class AppointmentUpdateInput(BaseModel):
    starts_at: datetime | None = None
    reason: str | None = Field(default=None, min_length=2, max_length=240)


class NoteInput(BaseModel):
    patient_id: UUID
    encounter_id: UUID | None = None
    body: str = Field(min_length=1)
    ai_draft: str | None = None


class NoteUpdateInput(BaseModel):
    body: str = Field(min_length=1)
    ai_draft: str | None = None


class RagQuestion(BaseModel):
    patient_id: UUID
    question: str = Field(min_length=3, max_length=2000)


class GeneralChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class GuestVoiceInput(BaseModel):
    audio_base64: str = Field(min_length=4, max_length=14_000_000)
    content_type: str = Field(default="audio/webm", pattern=r"^audio/webm$")
    language: str = Field(default="ar-EG", pattern=r"^(ar-EG|en-US)$")


class SSOStartInput(BaseModel):
    provider: str = "hospital_sso"
    email: str | None = None
    redirect_uri: str | None = None


class SSOCallbackInput(BaseModel):
    code: str
    state: str
    provider: str = "hospital_sso"


class SSOIdentityInput(BaseModel):
    provider: str = "hospital_sso"
    email: str | None = None
    password: str | None = None
    code: str | None = None
    state: str | None = None


class DemoLoginInput(BaseModel):
    role: str = Field(min_length=2, max_length=40)
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class WorkspaceCreateInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    department: str = Field(min_length=2, max_length=120)
    timezone: str = Field(min_length=2, max_length=80)


class DocumentInput(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str | None = None
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=80)


class MessageInput(BaseModel):
    patient_id: UUID
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    sender_type: str = Field(default="care_team", min_length=1, max_length=32)
    direction: str = Field(default="outbound", min_length=1, max_length=24)


class PortalMessageInput(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)


class CarePlanInput(BaseModel):
    patient_id: UUID
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1)
    status: str = Field(default="active", min_length=1, max_length=32)
    goals: list[str] = Field(default_factory=list)


class TaskInput(BaseModel):
    patient_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    assignee: str = Field(default="", min_length=0, max_length=120)
    priority: str = Field(default="medium", min_length=1, max_length=24)
    status: str = Field(default="pending", min_length=1, max_length=32)
    due_at: datetime | None = None


class PortalRegisterInput(BaseModel):
    patient_id: UUID
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class PortalLoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class PortalDocumentInput(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=80)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=8, max_length=128)


class InviteAcceptRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class MfaVerifyInput(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class RoleCreateInput(BaseModel):
    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)


class RoleAssignmentInput(BaseModel):
    role_id: UUID


class RolePermissionInput(BaseModel):
    permission_id: UUID


class SSOConfigurationInput(BaseModel):
    provider: str = Field(default="oidc", pattern="^(oidc|saml)$")
    issuer_url: str = Field(min_length=8, max_length=500)
    client_id: str = Field(min_length=2, max_length=255)
    client_secret: str | None = Field(default=None, min_length=1, max_length=500)
    enabled: bool = False


class EncounterCreateInput(BaseModel):
    patient_id: UUID
    encounter_type: str = Field(default="consultation", min_length=2, max_length=40)


class RecordingInput(BaseModel):
    content: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="audio/webm", min_length=3, max_length=80)


class TranscriptReviewInput(BaseModel):
    transcript_text: str = Field(min_length=1, max_length=200000)


def patient_public(patient: Patient) -> dict[str, object]:
    return {"id": patient.id, "patient_code": patient.patient_code, "medical_record_number": patient.medical_record_number, "given_name": patient.given_name, "family_name": patient.family_name, "department": patient.department, "project": patient.project, "date_of_birth": patient.date_of_birth, "gender": patient.gender, "condition": patient.condition, "care_status": patient.care_status, "created_at": patient.created_at}


async def owned_patient(session: AsyncSession, patient_id: UUID, organization_id: UUID) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None or patient.deleted_at is not None or patient.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


def patient_scope_matches(user, patient) -> bool:
    user_department = (getattr(user, "department", "") or "").strip().lower()
    patient_department = (getattr(patient, "department", "") or "").strip().lower()
    user_project = (getattr(user, "project", "") or "").strip().lower()
    patient_project = (getattr(patient, "project", "") or "").strip().lower()

    same_department = (not user_department) or (not patient_department) or (user_department == patient_department)
    same_project = (not user_project) or (not patient_project) or (user_project == patient_project)
    return same_department and same_project


async def ensure_patient_access(session: AsyncSession, patient_id: UUID, user, action: str) -> Patient:
    patient = await owned_patient(session, patient_id, user.organization_id)
    if not can_access_patient_scope(
        user.role,
        action,
        same_organization=True,
        same_department=patient_scope_matches(user, patient),
        same_project=patient_scope_matches(user, patient),
    ):
        raise HTTPException(status_code=403, detail=f"Role cannot {action} this patient")
    return patient


async def create_portal_session(session: AsyncSession, account: PatientPortalAccount) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=60)
    jti = uuid4().hex
    session.add(PatientPortalSession(portal_account_id=account.id, token_jti=jti, expires_at=expires))
    await session.flush()
    return jwt.encode({"sub": str(account.id), "patient_id": str(account.patient_id), "organization_id": str(account.organization_id), "role": "patient", "jti": jti, "exp": expires}, get_settings().secret_key, algorithm=get_settings().jwt_algorithm)


async def current_portal_account(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), session: AsyncSession = Depends(get_session)) -> PatientPortalAccount:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, get_settings().secret_key, algorithms=[get_settings().jwt_algorithm])
        account_id = UUID(payload["sub"])
        patient_id = UUID(payload["patient_id"])
        organization_id = UUID(payload["organization_id"])
        jti = payload["jti"]
    except (JWTError, KeyError, ValueError) as error:
        raise HTTPException(status_code=401, detail="Invalid patient portal token") from error

    portal_session = await session.scalar(select(PatientPortalSession).where(PatientPortalSession.token_jti == jti, PatientPortalSession.revoked_at.is_(None)))
    account = await session.get(PatientPortalAccount, account_id)
    expires_at = portal_session.expires_at if portal_session is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if account is None or portal_session is None or expires_at is None or expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Patient portal session expired")
    if account.organization_id != organization_id or account.patient_id != patient_id:
        raise HTTPException(status_code=401, detail="Patient portal token does not match this tenant or patient")

    patient = await session.get(Patient, patient_id)
    if patient is None or patient.organization_id != organization_id:
        raise HTTPException(status_code=401, detail="Patient portal token is not valid for this organization")

    return account


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readiness", tags=["system"])
async def readiness(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="Database is not ready") from error
    return {"status": "ready"}


@router.get("/metrics", tags=["system"])
async def metrics(user=Depends(require_permission("dashboard.read")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:

    patient_count = await session.scalar(select(func.count()).select_from(Patient).where(Patient.organization_id == user.organization_id))
    appointment_count = await session.scalar(select(func.count()).select_from(Appointment).where(Appointment.organization_id == user.organization_id))
    return {
        "app": "careos-api",
        "environment": "development" if not get_settings().is_production else "production",
        "deployment": get_settings().deployment_name,
        "roles": [user.role],
        "patients": int(patient_count or 0),
        "appointments": int(appointment_count or 0),
        "metrics_enabled": get_settings().metrics_enabled,
        "sso_ready": bool(get_settings().oidc_issuer_url),
    }


@router.get("/system/status", tags=["system"])
async def system_status() -> dict[str, object]:
    settings = get_settings()
    ai_provider = settings.ai_provider.strip().lower()
    ai_configured = ai_provider not in {"", "unconfigured", "sandbox"} and bool(
        settings.ai_api_key and (ai_provider == "openai" or settings.ai_api_url)
    )
    speech_provider = settings.speech_to_text_provider.strip().lower()
    if speech_provider in {"", "unconfigured"} and ai_provider == "openai":
        speech_provider = "openai"
    speech_api_key = settings.speech_to_text_api_key or (
        settings.ai_api_key if speech_provider == "openai" and ai_provider == "openai" else ""
    )
    speech_configured = speech_provider not in {"", "unconfigured"} and bool(
        speech_api_key and (speech_provider == "openai" or settings.speech_to_text_api_url)
    )
    smtp_configured = bool(settings.smtp_host and settings.smtp_from)
    storage_configured = settings.storage_backend.lower() == "filesystem" or bool(settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key)
    return {
        "app": settings.app_name,
        "environment": settings.app_env,
        "deployment": settings.deployment_name,
        "metrics_enabled": settings.metrics_enabled,
        "sso_ready": bool(settings.oidc_issuer_url and settings.oidc_client_id),
        "providers": {
            "ai": {"configured": ai_configured, "provider": settings.ai_provider},
            "speech_to_text": {"configured": speech_configured, "provider": speech_provider},
            "smtp": {"configured": smtp_configured},
            "storage": {"configured": storage_configured, "backend": settings.storage_backend},
        },
        "allowed_hosts": settings.allowed_hosts,
        "cors_origins": settings.cors_origins,
    }


@router.post("/auth/register", status_code=201, tags=["auth"])
async def register(request: RegisterRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    user, token = await register_user(session, request)
    return {"access_token": token, "token_type": "bearer", "user": public_user(user)}


@router.post("/auth/demo-login", tags=["auth"], include_in_schema=False)
async def demo_login(request: DemoLoginInput, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    if get_settings().is_production:
        raise HTTPException(status_code=404, detail="Demo login is disabled")

    demo_roles = {"admin", "doctor", "nurse", "receptionist", "hospital_director", "it_admin", "administrative_staff", "patient"}
    role = normalize_role(request.role)
    if role not in demo_roles:
        raise HTTPException(status_code=400, detail="Unsupported demo role")
    demo_credentials = {
        "admin": ("admin.demo", "Admin@123", "admin.demo@careos.example.com"),
        "doctor": ("doctor.demo", "Doctor@123", "doctor.demo@careos.example.com"),
        "nurse": ("nurse.demo", "Nurse@123", "nurse.demo@careos.example.com"),
        "receptionist": ("reception.demo", "Reception@123", "reception.demo@careos.example.com"),
        "hospital_director": ("director.demo", "Director@123", "director.demo@careos.example.com"),
        "it_admin": ("itadmin.demo", "ITAdmin@123", "itadmin.demo@careos.example.com"),
        "administrative_staff": ("staff.demo", "Staff@123", "staff.demo@careos.example.com"),
        "patient": ("patient.demo", "Patient@123", "patient.demo@careos.example.com"),
    }
    expected_username, expected_password, expected_email = demo_credentials[role]
    if request.username.strip().lower() != expected_username or request.password != expected_password:
        raise HTTPException(status_code=401, detail="Invalid demo credentials")

    organization = await session.scalar(select(Organization).where(Organization.name == "CareOS Demo Hospital"))
    if organization is None:
        organization = Organization(name="CareOS Demo Hospital", department="General Medicine", timezone="Africa/Cairo")
        session.add(organization)
        await session.flush()

    admin = await session.scalar(select(User).where(User.organization_id == organization.id, User.email == "demo-admin@careos.local"))
    if admin is None:
        admin = User(
            organization_id=organization.id,
            email="demo-admin@careos.local",
            full_name="CareOS Demo Admin",
            role="admin",
            department="Administration",
            project="Demo workspace",
            password_hash=password_hasher.hash(secrets.token_urlsafe(24)),
            onboarding_complete=True,
        )
        session.add(admin)
        await session.flush()
        await provision_role_assignments(session, admin)

    patient = await session.scalar(select(Patient).where(Patient.organization_id == organization.id, Patient.medical_record_number == "DEMO-001"))
    if patient is None:
        patient = Patient(
            organization_id=organization.id,
            department="General Medicine",
            project="Demo workspace",
            medical_record_number="DEMO-001",
            given_name="Mariam",
            family_name="Hassan",
            date_of_birth=date(1987, 4, 12),
            gender="female",
            condition="Hypertension follow-up",
            care_status="stable",
        )
        session.add(patient)
        await session.flush()

    if role == "patient":
        account = await session.scalar(select(PatientPortalAccount).where(PatientPortalAccount.email == expected_email))
        if account is None:
            account = PatientPortalAccount(
                organization_id=organization.id,
                patient_id=patient.id,
                email=expected_email,
                full_name="Mariam Hassan",
                password_hash=password_hasher.hash(secrets.token_urlsafe(24)),
            )
            session.add(account)
            await session.flush()
        portal_token = await create_portal_session(session, account)
        await session.commit()
        return {"demo_role": role, "portal_access_token": portal_token, "user": {"id": account.id, "patient_id": patient.id, "email": account.email, "full_name": account.full_name, "role": "patient"}}

    email = expected_email
    user = await session.scalar(select(User).where(User.organization_id == organization.id, User.email == email))
    if user is None:
        user = User(
            organization_id=organization.id,
            email=email,
            full_name={"admin": "Demo Administrator", "doctor": "Dr. Demo Clinician", "nurse": "Demo Nurse", "receptionist": "Demo Reception", "hospital_director": "Demo Hospital Director", "it_admin": "Demo IT Administrator", "administrative_staff": "Demo Operations Staff"}[role],
            role=role,
            department="General Medicine",
            project="Demo workspace",
            password_hash=password_hasher.hash(secrets.token_urlsafe(24)),
            onboarding_complete=True,
        )
        session.add(user)
        await session.flush()
    await provision_role_assignments(session, user)
    user._effective_permissions = await permissions_for_user(session, user)
    token = await _token_for(session, user)
    await session.commit()
    return {"demo_role": role, "access_token": token, "token_type": "bearer", "user": public_user(user)}


@router.post("/auth/login", tags=["auth"])
async def login(request: LoginRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    user, token = await authenticate(session, request)
    return {"access_token": token, "token_type": "bearer", "user": public_user(user)}


@router.post("/auth/password-reset/request", tags=["auth"])
async def request_password_reset(request: PasswordResetRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    user = await session.scalar(select(User).where(User.email == request.email.strip().lower()))
    response: dict[str, object] = {"accepted": True}
    if user is None:
        return response
    raw_token = secrets.token_urlsafe(32)
    session.add(PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw_token.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)))
    await session.commit()
    await enqueue_email(session, recipient=user.email, subject="CareOS password reset", body=f"Reset your CareOS password using this token: {raw_token}", organization_id=user.organization_id)
    if not get_settings().is_production:
        response["development_token"] = raw_token
    return response


@router.post("/auth/password-reset/confirm", tags=["auth"])
async def confirm_password_reset(request: PasswordResetConfirm, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    reset = await session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash, PasswordResetToken.used_at.is_(None)))
    expires_at = reset.expires_at.replace(tzinfo=timezone.utc) if reset is not None and reset.expires_at.tzinfo is None else reset.expires_at if reset is not None else None
    if reset is None or expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")
    user = await session.get(User, reset.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid password reset token")
    user.password_hash = password_hasher.hash(request.password)
    reset.used_at = datetime.now(timezone.utc)
    sessions = (await session.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)))).all()
    for auth_session in sessions:
        auth_session.revoked_at = datetime.now(timezone.utc)
    await session.commit()
    return {"reset": True}


@router.post("/auth/invitations/accept", tags=["auth"])
async def accept_invitation(request: InviteAcceptRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    invite = await session.scalar(select(TeamInvite).where(TeamInvite.token_hash == token_hash, TeamInvite.status == "pending"))
    invite_expires_at = invite.expires_at.replace(tzinfo=timezone.utc) if invite is not None and invite.expires_at is not None and invite.expires_at.tzinfo is None else invite.expires_at if invite is not None else None
    if invite is None or invite_expires_at is None or invite_expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")
    existing = await session.scalar(select(User).where(User.email == invite.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account already exists for this invitation")
    user = User(organization_id=invite.organization_id, email=invite.email, full_name=request.full_name, role=normalize_role(invite.role), password_hash=password_hasher.hash(request.password), onboarding_complete=True)
    session.add(user)
    await session.flush()
    await provision_role_assignments(session, user)
    invite.status = "accepted"
    invite.accepted_at = datetime.now(timezone.utc)
    token = await _token_for(session, user)
    await session.commit()
    return {"access_token": token, "token_type": "bearer", "user": public_user(user)}


@router.post("/auth/sso/start", tags=["auth"])
async def start_sso(request: SSOStartInput) -> dict[str, str]:
    adapter = HospitalSSOAdapter(provider_name=request.provider)
    nonce = secrets.token_urlsafe(32)
    state = jwt.encode(
        {"nonce": nonce, "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        get_settings().secret_key,
        algorithm=get_settings().jwt_algorithm,
    )
    redirect_uri = request.redirect_uri or adapter.callback_url
    try:
        redirect_url = adapter.build_redirect_url(state=state, nonce=nonce, redirect_uri=redirect_uri)
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"provider": request.provider, "redirect_url": redirect_url, "state": state, "nonce": nonce}


@router.post("/auth/sso/callback", tags=["auth"])
async def sso_callback(request: SSOCallbackInput, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    adapter = HospitalSSOAdapter(provider_name=request.provider)
    try:
        claims = adapter.exchange_code_for_claims(code=request.code, state=request.state)
    except ValueError as error:
        raise HTTPException(status_code=401, detail="External identity verification failed") from error
    mapped = adapter.map_claims_to_org_workspace(claims)
    user = await ensure_sso_user(session, claims)
    token = await _token_for(session, user)
    return {
        "provider": request.provider,
        "status": "authenticated",
        "claims": claims.__dict__,
        "mapped": mapped,
        "access_token": token,
        "token_type": "bearer",
        "user": public_user(user),
    }


async def ensure_sso_user(session: AsyncSession, claims) -> User:
    email = (claims.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="SSO claim is missing an email")

    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        domain = (claims.organization_domain or (email.split("@", 1)[1] if "@" in email else "citycare.org")).strip().lower()
        organization_name = domain.split(".")[0].title() + " Health"
        organization = await session.scalar(select(Organization).where(Organization.name == organization_name))
        if organization is None:
            organization = Organization(name=organization_name, department="General Medicine", timezone="UTC")
            session.add(organization)
            await session.flush()

        user = User(
            organization_id=organization.id,
            department="General Medicine",
            project="Outpatient",
            email=email,
            full_name=claims.full_name or email.split("@", 1)[0].replace(".", " ").title(),
            role=normalize_role(claims.role or "physician"),
            password_hash=password_hasher.hash(f"__sso__{claims.provider_user_id or email}"),
            onboarding_complete=True,
        )
        session.add(user)
        await session.flush()
        await provision_role_assignments(session, user)
        await write_audit(session, user, "sso.user_synced", "organization")

    user.role = normalize_role(claims.role or user.role)
    user.full_name = claims.full_name or user.full_name
    user.onboarding_complete = True
    await write_audit(session, user, "sso.user_logged_in", "organization")
    await session.commit()
    return user


@router.post("/auth/sso", tags=["auth"])
async def login_sso(request: SSOIdentityInput, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    provider = request.provider or "hospital_sso"
    if request.code and request.state:
        adapter = HospitalSSOAdapter(provider_name=provider)
        claims = adapter.exchange_code_for_claims(code=request.code, state=request.state)
    else:
        raise HTTPException(status_code=400, detail="SSO login requires a verified callback code and state")

    user = await ensure_sso_user(session, claims)
    token = await _token_for(session, user)
    return {"access_token": token, "token_type": "bearer", "user": public_user(user)}


@router.get("/me", tags=["auth"])
async def me(user=Depends(current_user)) -> dict[str, object]:
    return public_user(user)


@router.post("/auth/verify-email", tags=["auth"])
async def verify_email(request: VerifyEmailRequest, user=Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    normalized = str(request.email).strip().lower()
    if normalized != user.email.lower():
        raise HTTPException(status_code=403, detail="Only the current account email can be verified")
    user.email_verified = True
    await write_audit(session, user, "auth.email_verified", user.email)
    await session.commit()
    return {"email": user.email, "email_verified": True}


@router.post("/auth/logout", status_code=204, tags=["auth"])
async def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), user=Depends(current_user), session: AsyncSession = Depends(get_session)) -> None:
    if credentials is not None:
        await revoke_token(session, credentials, user)


@router.post("/auth/mfa/enroll", tags=["auth"])
async def enroll_mfa(user=Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    secret = generate_totp_secret()
    user.mfa_secret_ref = encrypt_mfa_secret(secret)
    user.mfa_enabled = False
    await session.commit()
    issuer = "CareOS"
    uri = f"otpauth://totp/{issuer}:{user.email}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    return {"secret": secret, "otpauth_uri": uri, "enabled": False}


@router.post("/auth/mfa/verify", tags=["auth"])
async def verify_mfa(request: MfaVerifyInput, user=Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    try:
        secret = decrypt_mfa_secret(user.mfa_secret_ref or "")
    except Exception:
        secret = ""
    if not secret or not verify_totp(secret, request.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")
    user.mfa_enabled = True
    user.mfa_enrolled_at = datetime.now(timezone.utc)
    recovery_codes = [secrets.token_hex(5) for _ in range(10)]
    user.mfa_recovery_codes = json.dumps([hashlib.sha256(code.encode("ascii")).hexdigest() for code in recovery_codes])
    await write_audit(session, user, "auth.mfa_enabled", "account")
    await session.commit()
    return {"enabled": True, "recovery_codes": recovery_codes}


@router.post("/auth/mfa/recovery-codes", tags=["auth"])
async def regenerate_mfa_recovery_codes(user=Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    if not user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA must be enabled before recovery codes can be generated")
    recovery_codes = [secrets.token_hex(5) for _ in range(10)]
    user.mfa_recovery_codes = json.dumps([hashlib.sha256(code.encode("ascii")).hexdigest() for code in recovery_codes])
    await write_audit(session, user, "auth.mfa_recovery_codes_regenerated", "account")
    await session.commit()
    return {"recovery_codes": recovery_codes}


@router.get("/organization", tags=["onboarding"])
async def get_organization(user=Depends(require_permission("hospital.settings.view")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    organization = await session.get(Organization, user.organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {"id": organization.id, "name": organization.name, "department": organization.department, "timezone": organization.timezone, "onboarding_complete": user.onboarding_complete}


@router.get("/workspace", tags=["onboarding"])
async def get_workspace(user=Depends(require_permission("hospital.settings.view")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    organization = await session.get(Organization, user.organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {
        "id": organization.id,
        "organization_id": organization.id,
        "name": organization.name,
        "department": organization.department,
        "timezone": organization.timezone,
        "onboarding_complete": user.onboarding_complete,
    }


@router.post("/workspace", status_code=201, tags=["onboarding"])
async def create_workspace(request: WorkspaceCreateInput, user=Depends(require_permission("hospital.settings.manage")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    organization = await session.get(Organization, user.organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    organization.name = request.name
    organization.department = request.department
    organization.timezone = request.timezone
    user.onboarding_complete = True
    await write_audit(session, user, "workspace.created", request.name)
    await session.commit()
    return {
        "id": organization.id,
        "organization_id": organization.id,
        "name": organization.name,
        "department": organization.department,
        "timezone": organization.timezone,
        "onboarding_complete": user.onboarding_complete,
    }


@router.patch("/organization", tags=["onboarding"])
async def update_organization(
    request: OrganizationUpdate,
    user=Depends(require_permission("hospital.settings.manage")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str | object]:
    organization = await session.get(Organization, user.organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    for field, value in request.model_dump().items():
        setattr(organization, field, value)
    user.onboarding_complete = True
    await write_audit(session, user, "organization.updated", organization.name)
    await session.commit()
    return {"id": organization.id, "name": organization.name, "department": organization.department, "timezone": organization.timezone}


@router.get("/team", tags=["team"])
async def team(user=Depends(require_permission("users.view")), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    members = (await session.scalars(select(User).where(User.organization_id == user.organization_id))).all()
    return [public_user(member) for member in members]


@router.get("/roles", tags=["rbac"])
async def list_roles(user=Depends(require_permission("roles.view")), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    roles = (await session.scalars(select(Role).where(Role.organization_id == user.organization_id).order_by(Role.key))).all()
    return [{"id": role.id, "key": role.key, "name": role.name, "description": role.description} for role in roles]


@router.post("/roles", status_code=201, tags=["rbac"])
async def create_role(request: RoleCreateInput, user=Depends(require_permission("roles.manage")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    existing = await session.scalar(select(Role).where(Role.organization_id == user.organization_id, Role.key == request.key))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Role already exists")
    role = Role(organization_id=user.organization_id, key=request.key, name=request.name, description=request.description)
    session.add(role)
    await session.flush()
    await write_audit(session, user, "role.created", str(role.id))
    await session.commit()
    return {"id": role.id, "key": role.key, "name": role.name, "description": role.description}


@router.get("/permissions", tags=["rbac"])
async def list_permissions(user=Depends(require_permission("permissions.view")), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    permissions = (await session.scalars(select(Permission).order_by(Permission.key))).all()
    if permissions:
        return [{"id": permission.id, "key": permission.key, "description": permission.description} for permission in permissions]
    return [{"id": None, "key": key, "description": ""} for key in sorted({item for values in ROLE_PERMISSIONS.values() for item in values})]


@router.get("/organization/sso", tags=["sso"])
async def get_sso_configuration(user=Depends(require_permission("sso.view")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    configuration = await session.scalar(select(SSOConfiguration).where(SSOConfiguration.organization_id == user.organization_id))
    if configuration is None:
        return {"configured": False, "provider": None, "issuer_url": None, "client_id": None, "enabled": False}
    return {"configured": True, "provider": configuration.provider, "issuer_url": configuration.issuer_url, "client_id": configuration.client_id, "enabled": configuration.enabled}


@router.put("/organization/sso", tags=["sso"])
async def update_sso_configuration(request: SSOConfigurationInput, user=Depends(require_permission("sso.manage")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    configuration = await session.scalar(select(SSOConfiguration).where(SSOConfiguration.organization_id == user.organization_id))
    if configuration is None:
        configuration = SSOConfiguration(organization_id=user.organization_id, provider=request.provider, issuer_url=request.issuer_url, client_id=request.client_id, enabled=request.enabled)
        session.add(configuration)
    else:
        configuration.provider = request.provider
        configuration.issuer_url = request.issuer_url
        configuration.client_id = request.client_id
        configuration.enabled = request.enabled
    if request.client_secret:
        configuration.encrypted_client_secret = encrypt_mfa_secret(request.client_secret)
    await write_audit(session, user, "sso.configuration_updated", str(user.organization_id))
    await session.commit()
    return {"configured": True, "provider": configuration.provider, "issuer_url": configuration.issuer_url, "client_id": configuration.client_id, "enabled": configuration.enabled}


@router.post("/roles/{role_id}/permissions", status_code=201, tags=["rbac"])
async def grant_role_permission(role_id: UUID, request: RolePermissionInput, user=Depends(require_permission("roles.manage")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    role = await session.get(Role, role_id)
    permission = await session.get(Permission, request.permission_id)
    if role is None or permission is None or role.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Role or permission not found")
    existing = await session.scalar(select(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_id == permission.id))
    if existing is None:
        session.add(RolePermission(role_id=role.id, permission_id=permission.id))
        await write_audit(session, user, "role.permission_granted", f"{role.id}:{permission.id}")
        await session.commit()
    return {"role_id": role.id, "permission_id": permission.id, "granted": True}


@router.post("/users/{user_id}/roles", status_code=201, tags=["rbac"])
async def assign_user_role(user_id: UUID, request: RoleAssignmentInput, user=Depends(require_permission("roles.assign")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    target = await session.get(User, user_id)
    role = await session.get(Role, request.role_id)
    if target is None or role is None or target.organization_id != user.organization_id or role.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="User or role not found")
    assignment = await session.scalar(select(UserRole).where(UserRole.user_id == target.id, UserRole.role_id == role.id))
    if assignment is None:
        session.add(UserRole(user_id=target.id, role_id=role.id))
        await write_audit(session, user, "user.role_assigned", f"{target.id}:{role.id}")
        await session.commit()
    return {"user_id": target.id, "role_id": role.id, "assigned": True}


@router.post("/team/invites", status_code=201, tags=["team"])
async def invite_member(request: InviteRequest, user=Depends(require_permission("users.invite")), session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    raw_token = secrets.token_urlsafe(32)
    invite = TeamInvite(organization_id=user.organization_id, email=str(request.email).lower(), role=request.role, token_hash=hashlib.sha256(raw_token.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    session.add(invite)
    await write_audit(session, user, "team.invited", str(request.email))
    await session.commit()
    organization = await session.get(Organization, user.organization_id)
    await enqueue_email(session, recipient=str(request.email), subject=f"CareOS invitation to {organization.name if organization else 'CareOS'}", body=f"You have been invited as {request.role}. Invitation token: {raw_token}", organization_id=user.organization_id)
    response: dict[str, str] = {"email": str(request.email), "role": request.role, "status": "pending"}
    if not get_settings().is_production:
        response["development_token"] = raw_token
    return response


@router.get("/audit-events", response_model=list[AuditEventResponse], tags=["audit"])
async def audit_log(user=Depends(require_permission("audit_logs.view")), session: AsyncSession = Depends(get_session)) -> list[AuditEvent]:
    return list((await session.scalars(select(AuditEvent).where(AuditEvent.organization_id == user.organization_id).order_by(AuditEvent.created_at.desc()))).all())


@router.post("/system/audit/cleanup", tags=["system"])
async def cleanup_audit_events(user=Depends(require_permission("audit_logs.view")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    retention_cutoff = datetime.now(timezone.utc) - timedelta(days=get_settings().audit_retention_days)
    deleted = await session.execute(
        select(AuditEvent).where(AuditEvent.organization_id == user.organization_id, AuditEvent.created_at < retention_cutoff)
    )
    records = deleted.scalars().all()
    for record in records:
        await session.delete(record)
    await session.commit()
    return {"deleted": len(records), "retention_days": get_settings().audit_retention_days}


@router.get("/notifications", tags=["notifications"])
async def notifications(user=Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    records = (await session.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50))).all()
    return [{"id": item.id, "kind": item.kind, "title": item.title, "body": item.body, "read": item.read, "created_at": item.created_at} for item in records]


@router.patch("/notifications/{notification_id}/read", tags=["notifications"])
async def mark_notification_read(notification_id: UUID, user=Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read = True
    await session.commit()
    return {"read": True}


@router.get("/dashboard", tags=["clinical"])
async def dashboard(user=Depends(require_permission("dashboard.read")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:

    patient_statement = select(Patient).where(Patient.organization_id == user.organization_id, Patient.deleted_at.is_(None))
    if user.department or user.project:
        patient_statement = patient_statement.where(
            (Patient.department == "") | (Patient.department == user.department)
        )
        if user.project:
            patient_statement = patient_statement.where((Patient.project == "") | (Patient.project == user.project))

    patients_in_scope = (await session.scalars(patient_statement.order_by(Patient.family_name, Patient.given_name))).all()
    patient_count = len(patients_in_scope)
    upcoming = list((await session.scalars(select(Appointment).join(Patient, Appointment.patient_id == Patient.id).where(Appointment.organization_id == user.organization_id, Patient.organization_id == user.organization_id, Appointment.starts_at >= datetime.now(timezone.utc)).order_by(Appointment.starts_at).limit(8))).all())
    followups = [item for item in patients_in_scope if item.care_status in {"follow_up_due", "needs_attention"}][:5]
    return {"patient_count": patient_count, "upcoming_appointments": [appointment_public(item) for item in upcoming], "followups": [patient_public(item) for item in followups]}


@router.get("/patients", tags=["clinical"])
async def list_patients(q: str = "", page: int = Query(default=1, ge=1, le=100000), page_size: int = Query(default=50, ge=1, le=100), user=Depends(require_permission("patients.view")), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    statement = select(Patient).where(Patient.organization_id == user.organization_id, Patient.deleted_at.is_(None))
    if user.department or user.project:
        statement = statement.where((Patient.department == "") | (Patient.department == user.department))
        if user.project:
            statement = statement.where((Patient.project == "") | (Patient.project == user.project))
    statement = statement.order_by(Patient.family_name, Patient.given_name)
    if q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where((Patient.given_name.ilike(pattern)) | (Patient.family_name.ilike(pattern)) | (Patient.patient_code.ilike(pattern)) | (Patient.medical_record_number.ilike(pattern)) | (cast(Patient.date_of_birth, String).ilike(pattern)))
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    return [patient_public(item) for item in (await session.scalars(statement)).all()]


@router.post("/patients", status_code=201, tags=["clinical"])
async def create_patient(request: PatientInput, user=Depends(require_permission("patients.create")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    existing = await session.scalar(select(Patient).where(Patient.organization_id == user.organization_id, Patient.medical_record_number == request.medical_record_number))
    if existing:
        raise HTTPException(status_code=409, detail="Medical record number already exists")
    patient = Patient(organization_id=user.organization_id, **request.model_dump())
    session.add(patient); await session.flush(); await write_audit(session, user, "patient.created", str(patient.id)); await session.commit()
    return patient_public(patient)


@router.get("/patients/{patient_id}", tags=["clinical"])
async def get_patient(patient_id: UUID, user=Depends(require_permission("patients.view")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    patient = await ensure_patient_access(session, patient_id, user, "read")
    notes = list((await session.scalars(select(ClinicalNote).where(ClinicalNote.patient_id == patient.id, ClinicalNote.organization_id == user.organization_id, ClinicalNote.deleted_at.is_(None)).order_by(ClinicalNote.created_at.desc()))).all())
    documents = list((await session.scalars(select(PatientDocument).where(PatientDocument.patient_id == patient.id, PatientDocument.organization_id == user.organization_id, PatientDocument.deleted_at.is_(None)).order_by(PatientDocument.created_at.desc()))).all())
    return {**patient_public(patient), "notes": [note_public(note) for note in notes], "documents": [{"id": doc.id, "encounter_id": doc.encounter_id, "filename": doc.filename, "ocr_status": doc.ocr_status, "extracted_text": doc.extracted_text, "download_url": doc.download_url} for doc in documents]}


@router.get("/patients/{patient_id}/profile", tags=["clinical"])
async def get_patient_profile(patient_id: UUID, user=Depends(require_permission("patients.view")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await ensure_patient_access(session, patient_id, user, "read")
    profile = await session.scalar(select(PatientProfile).where(PatientProfile.patient_id == patient_id, PatientProfile.organization_id == user.organization_id))
    if profile is None:
        return {"patient_id": patient_id, "phone": None, "email": None, "address": None, "emergency_contact": None}
    return {"patient_id": profile.patient_id, "phone": profile.phone, "email": profile.email, "address": profile.address, "emergency_contact": profile.emergency_contact}


@router.put("/patients/{patient_id}/profile", tags=["clinical"])
async def update_patient_profile(patient_id: UUID, request: PatientProfileInput, user=Depends(require_permission("patients.update")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await ensure_patient_access(session, patient_id, user, "write")
    profile = await session.scalar(select(PatientProfile).where(PatientProfile.patient_id == patient_id, PatientProfile.organization_id == user.organization_id))
    if profile is None:
        profile = PatientProfile(organization_id=user.organization_id, patient_id=patient_id, **request.model_dump())
        session.add(profile)
    else:
        for field, value in request.model_dump().items():
            setattr(profile, field, value)
    await write_audit(session, user, "patient.profile_updated", str(patient_id))
    await session.commit()
    return {"patient_id": profile.patient_id, "phone": profile.phone, "email": profile.email, "address": profile.address, "emergency_contact": profile.emergency_contact}


@router.patch("/patients/{patient_id}", tags=["clinical"])
async def update_patient(patient_id: UUID, request: PatientInput, user=Depends(require_permission("patients.update")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    patient = await ensure_patient_access(session, patient_id, user, "write")
    for key, value in request.model_dump().items(): setattr(patient, key, value)
    await write_audit(session, user, "patient.updated", str(patient.id)); await session.commit(); return patient_public(patient)


def appointment_public(item: Appointment) -> dict[str, object]:
    return {"id": item.id, "patient_id": item.patient_id, "starts_at": item.starts_at, "reason": item.reason, "status": item.status, "reminder_status": item.reminder_status}


@router.get("/appointments", tags=["clinical"])
async def list_appointments(status: str | None = None, from_at: datetime | None = None, to_at: datetime | None = None, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100), user=Depends(require_permission("appointments.view")), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    statement = select(Appointment).where(Appointment.organization_id == user.organization_id)
    if status:
        if status not in {"pending", "confirmed", "arrived", "cancelled"}:
            raise HTTPException(status_code=422, detail="Invalid appointment status")
        statement = statement.where(Appointment.status == status)
    if from_at:
        statement = statement.where(Appointment.starts_at >= from_at)
    if to_at:
        statement = statement.where(Appointment.starts_at <= to_at)
    statement = statement.order_by(Appointment.starts_at.desc()).offset((page - 1) * page_size).limit(page_size)
    records = (await session.scalars(statement)).all()
    return [appointment_public(item) for item in records]


@router.post("/appointments", status_code=201, tags=["clinical"])
async def create_appointment(request: AppointmentInput, user=Depends(require_permission("appointments.create")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await ensure_patient_access(session, request.patient_id, user, "appointments")
    if request.starts_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Appointment must be scheduled in the future")
    if request.status not in {"pending", "confirmed"}:
        raise HTTPException(status_code=422, detail="New appointments must be pending or confirmed")
    conflict = await session.scalar(select(Appointment).where(Appointment.organization_id == user.organization_id, Appointment.starts_at == request.starts_at, Appointment.status.not_in(["cancelled"])))
    if conflict: raise HTTPException(status_code=409, detail="An appointment already exists at this time")
    item = Appointment(organization_id=user.organization_id, **request.model_dump()); session.add(item); await session.flush()
    session.add(ReminderJob(organization_id=user.organization_id, appointment_id=item.id, scheduled_for=item.starts_at, channel="sandbox")); item.reminder_status = "queued"
    await write_audit(session, user, "appointment.created", str(item.id)); await session.commit(); return appointment_public(item)


@router.patch("/appointments/{appointment_id}/status", tags=["clinical"])
async def update_appointment_status(appointment_id: UUID, request: Request, status: str | None = Query(None), user=Depends(require_permission("appointments.update")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    effective_status = status
    if not effective_status:
        try:
            body = await request.json()
            if isinstance(body, dict):
                effective_status = body.get("status")
        except Exception:
            pass
    if not effective_status:
        raise HTTPException(status_code=422, detail="Invalid appointment status")
    item = await session.get(Appointment, appointment_id)
    if item is None or item.organization_id != user.organization_id: raise HTTPException(status_code=404, detail="Appointment not found")
    if effective_status not in {"pending", "confirmed", "arrived", "cancelled"}: raise HTTPException(status_code=422, detail="Invalid appointment status")
    if item.status == "cancelled" and effective_status != "cancelled": raise HTTPException(status_code=409, detail="Cancelled appointments cannot be reopened")
    await ensure_patient_access(session, item.patient_id, user, "appointments")
    item.status = effective_status; await write_audit(session, user, "appointment.status_updated", str(item.id)); await session.commit(); return appointment_public(item)


@router.patch("/appointments/{appointment_id}", tags=["clinical"])
async def update_appointment(appointment_id: UUID, request: AppointmentUpdateInput, user=Depends(require_permission("appointments.update")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    item = await session.get(Appointment, appointment_id)
    if item is None or item.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if item.status == "cancelled":
        raise HTTPException(status_code=409, detail="Cancelled appointments cannot be rescheduled")
    await ensure_patient_access(session, item.patient_id, user, "appointments")
    if request.starts_at is not None:
        if request.starts_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="Appointment must be scheduled in the future")
        conflict = await session.scalar(select(Appointment).where(Appointment.organization_id == user.organization_id, Appointment.id != item.id, Appointment.starts_at == request.starts_at, Appointment.status.not_in(["cancelled"])))
        if conflict:
            raise HTTPException(status_code=409, detail="An appointment already exists at this time")
        item.starts_at = request.starts_at
        item.reminder_status = "queued"
    if request.reason is not None:
        item.reason = request.reason
    await write_audit(session, user, "appointment.rescheduled", str(item.id))
    await session.commit()
    return appointment_public(item)


@router.post("/encounters", status_code=201, tags=["encounters"])
async def create_encounter(request: EncounterCreateInput, user=Depends(require_permission("encounters.create")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    patient = await ensure_patient_access(session, request.patient_id, user, "read")
    encounter = Encounter(organization_id=user.organization_id, patient_id=patient.id, clinician_id=user.id, encounter_type=request.encounter_type)
    session.add(encounter)
    await session.flush()
    await write_audit(session, user, "encounter.created", str(encounter.id))
    await session.commit()
    return {"id": encounter.id, "organization_id": encounter.organization_id, "patient_id": encounter.patient_id, "clinician_id": encounter.clinician_id, "encounter_type": encounter.encounter_type, "status": encounter.status, "started_at": encounter.started_at, "ended_at": encounter.ended_at}


@router.get("/encounters/{encounter_id}", tags=["encounters"])
async def get_encounter(encounter_id: UUID, user=Depends(require_permission("encounters.view")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    encounter = await session.get(Encounter, encounter_id)
    if encounter is None or encounter.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Encounter not found")
    await ensure_patient_access(session, encounter.patient_id, user, "read")
    return {"id": encounter.id, "organization_id": encounter.organization_id, "patient_id": encounter.patient_id, "clinician_id": encounter.clinician_id, "encounter_type": encounter.encounter_type, "status": encounter.status, "started_at": encounter.started_at, "ended_at": encounter.ended_at}


@router.post("/encounters/{encounter_id}/recordings", status_code=201, tags=["recordings"])
async def upload_recording(encounter_id: UUID, request: RecordingInput, user=Depends(require_permission("recordings.create")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    encounter = await session.get(Encounter, encounter_id)
    if encounter is None or encounter.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Encounter not found")
    await ensure_patient_access(session, encounter.patient_id, user, "notes")
    try:
        content = base64.b64decode(request.content, validate=True)
        storage_key, _ = StorageService().save_document(organization_id=str(user.organization_id), patient_id=str(encounter.patient_id), filename=request.filename, content=content, content_type=request.content_type)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail="Recording upload could not be stored") from error
    audio = AudioFile(organization_id=user.organization_id, patient_id=encounter.patient_id, encounter_id=encounter.id, storage_key=storage_key, content_type=request.content_type, size_bytes=len(content))
    session.add(audio)
    await session.flush()
    transcript = Transcript(organization_id=user.organization_id, patient_id=encounter.patient_id, encounter_id=encounter.id, audio_file_id=audio.id, provider=get_settings().speech_to_text_provider, status="UPLOADED")
    session.add(transcript)
    await session.flush()
    session.add(TranscriptionJob(organization_id=user.organization_id, audio_file_id=audio.id, transcript_id=transcript.id))
    await write_audit(session, user, "recording.uploaded", str(audio.id))
    await session.commit()
    return {"id": audio.id, "encounter_id": audio.encounter_id, "patient_id": audio.patient_id, "content_type": audio.content_type, "size_bytes": audio.size_bytes, "transcript_id": transcript.id, "transcript_status": transcript.status}


@router.get("/transcripts/{transcript_id}", tags=["transcripts"])
async def get_transcript(transcript_id: UUID, user=Depends(require_permission("transcripts.view")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    transcript = await session.get(Transcript, transcript_id)
    if transcript is None or transcript.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Transcript not found")
    await ensure_patient_access(session, transcript.patient_id, user, "read")
    return {"id": transcript.id, "encounter_id": transcript.encounter_id, "audio_file_id": transcript.audio_file_id, "provider": transcript.provider, "language": transcript.language, "dialect": transcript.dialect, "transcript_text": transcript.transcript_text, "status": transcript.status, "confidence": transcript.confidence, "error_code": transcript.error_code, "created_at": transcript.created_at, "completed_at": transcript.completed_at}


@router.post("/recordings/{audio_id}/transcribe", status_code=202, tags=["transcripts"])
async def transcribe_recording(audio_id: UUID, user=Depends(require_permission("transcripts.create")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    audio = await session.get(AudioFile, audio_id)
    if audio is None or audio.deleted_at is not None or audio.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Recording not found")
    await ensure_patient_access(session, audio.patient_id, user, "notes")
    transcript = await session.scalar(select(Transcript).where(Transcript.audio_file_id == audio.id, Transcript.organization_id == user.organization_id))
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    job = await session.scalar(select(TranscriptionJob).where(TranscriptionJob.audio_file_id == audio.id, TranscriptionJob.organization_id == user.organization_id))
    if job is None:
        job = TranscriptionJob(organization_id=user.organization_id, audio_file_id=audio.id, transcript_id=transcript.id)
        session.add(job)
    if job.status == "COMPLETED":
        return {"id": transcript.id, "status": transcript.status, "transcript_text": transcript.transcript_text, "confidence": transcript.confidence, "provider": transcript.provider}
    transcript.status = "TRANSCRIBING"
    job.status = "QUEUED"
    job.available_at = datetime.now(timezone.utc)
    await session.commit()
    return {"id": transcript.id, "status": "QUEUED", "transcript_text": transcript.transcript_text, "confidence": transcript.confidence, "provider": transcript.provider}


@router.patch("/transcripts/{transcript_id}/review", tags=["transcripts"])
async def review_transcript(transcript_id: UUID, request: TranscriptReviewInput, user=Depends(require_permission("transcripts.update")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    transcript = await session.get(Transcript, transcript_id)
    if transcript is None or transcript.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Transcript not found")
    await ensure_patient_access(session, transcript.patient_id, user, "notes")
    latest_version = await session.scalar(select(func.max(TranscriptVersion.version)).where(TranscriptVersion.transcript_id == transcript.id, TranscriptVersion.organization_id == user.organization_id))
    version = int(latest_version or 0) + 1
    session.add(TranscriptVersion(organization_id=user.organization_id, transcript_id=transcript.id, version=version, transcript_text=request.transcript_text, editor_id=user.id))
    await write_audit(session, user, "transcript.reviewed", str(transcript.id))
    await session.commit()
    return {"id": transcript.id, "version": version, "transcript_text": request.transcript_text, "status": "REVIEWED"}


def note_public(note: ClinicalNote) -> dict[str, object]:
    return {"id": note.id, "patient_id": note.patient_id, "encounter_id": note.encounter_id, "body": note.body, "ai_draft": note.ai_draft, "status": note.status, "version": note.version, "signed_at": note.signed_at, "created_at": note.created_at}


@router.post("/clinical-notes", status_code=201, tags=["clinical"])
async def create_note(request: NoteInput, user=Depends(require_permission("clinical_notes.create")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await ensure_patient_access(session, request.patient_id, user, "notes")
    if request.encounter_id is not None:
        encounter = await session.get(Encounter, request.encounter_id)
        if encounter is None or encounter.organization_id != user.organization_id or encounter.patient_id != request.patient_id or encounter.status != "active":
            raise HTTPException(status_code=404, detail="Active encounter not found for this patient")
    note = ClinicalNote(organization_id=user.organization_id, author_id=user.id, **request.model_dump()); session.add(note); await session.flush()
    session.add(ClinicalNoteVersion(organization_id=user.organization_id, clinical_note_id=note.id, version=1, body=note.body, ai_draft=note.ai_draft, status=note.status, author_id=user.id))
    await write_audit(session, user, "clinical_note.created", str(note.id)); await session.commit(); return note_public(note)


@router.patch("/clinical-notes/{note_id}", tags=["clinical"])
async def update_note(note_id: UUID, request: NoteUpdateInput, user=Depends(require_permission("clinical_notes.update")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    note = await session.get(ClinicalNote, note_id)
    if note is None or note.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Clinical note not found")
    if note.status == "signed":
        raise HTTPException(status_code=409, detail="Approved clinical notes cannot be edited")
    await ensure_patient_access(session, note.patient_id, user, "notes")
    note.body = request.body
    note.ai_draft = request.ai_draft
    note.version += 1
    session.add(ClinicalNoteVersion(organization_id=user.organization_id, clinical_note_id=note.id, version=note.version, body=note.body, ai_draft=note.ai_draft, status="DRAFT", author_id=user.id))
    await write_audit(session, user, "clinical_note.updated", str(note.id))
    await session.commit()
    return note_public(note)


@router.post("/clinical-notes/{note_id}/summary", tags=["clinical"])
async def generate_summary(note_id: UUID, user=Depends(require_permission("clinical_notes.update")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    note = await session.get(ClinicalNote, note_id)
    if note is None or note.organization_id != user.organization_id: raise HTTPException(status_code=404, detail="Clinical note not found")
    await ensure_patient_access(session, note.patient_id, user, "notes")
    try:
        result = await summary_provider.summarize(note.body)
    except Exception as error:
        raise HTTPException(status_code=503, detail="AI clinical note service is currently unavailable") from error
    note.ai_draft = result.draft; note.version += 1
    session.add(ClinicalNoteVersion(organization_id=user.organization_id, clinical_note_id=note.id, version=note.version, body=note.body, ai_draft=note.ai_draft, status="DRAFT", author_id=user.id))
    await write_audit(session, user, "clinical_note.summary_generated", str(note.id)); await session.commit(); return {**note_public(note), "provider": result.provider}


@router.post("/clinical-notes/{note_id}/sign", tags=["clinical"])
async def sign_note(note_id: UUID, user=Depends(require_permission("clinical_notes.approve")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    note = await session.get(ClinicalNote, note_id)
    if note is None or note.organization_id != user.organization_id: raise HTTPException(status_code=404, detail="Clinical note not found")
    await ensure_patient_access(session, note.patient_id, user, "notes")
    if note.status == "signed":
        return note_public(note)
    note.status = "signed"; note.signed_at = datetime.now(timezone.utc); note.version += 1
    session.add(ClinicalNoteVersion(organization_id=user.organization_id, clinical_note_id=note.id, version=note.version, body=note.body, ai_draft=note.ai_draft, status="APPROVED", author_id=user.id))
    await write_audit(session, user, "clinical_note.approved", str(note.id)); await session.commit(); return note_public(note)


@router.post("/clinical-notes/{note_id}/approve", tags=["clinical"])
async def approve_note(note_id: UUID, user=Depends(require_permission("clinical_notes.approve")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    return await sign_note(note_id, user, session)


@router.get("/clinical-notes/{note_id}/versions", tags=["clinical"])
async def list_note_versions(note_id: UUID, user=Depends(require_permission("clinical_notes.view")), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    note = await session.get(ClinicalNote, note_id)
    if note is None or note.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Clinical note not found")
    await ensure_patient_access(session, note.patient_id, user, "notes")
    versions = (await session.scalars(select(ClinicalNoteVersion).where(ClinicalNoteVersion.clinical_note_id == note.id, ClinicalNoteVersion.organization_id == user.organization_id).order_by(ClinicalNoteVersion.version))).all()
    return [{"id": item.id, "version": item.version, "body": item.body, "ai_draft": item.ai_draft, "status": item.status, "author_id": item.author_id, "created_at": item.created_at} for item in versions]


@router.post("/clinical-notes/{note_id}/document", status_code=201, tags=["documents"])
async def generate_note_document(note_id: UUID, user=Depends(require_permission("documents.create")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    note = await session.get(ClinicalNote, note_id)
    if note is None or note.organization_id != user.organization_id or note.status != "signed":
        raise HTTPException(status_code=409, detail="Only approved clinical notes can generate documents")
    patient = await ensure_patient_access(session, note.patient_id, user, "documents")
    organization = await session.get(Organization, user.organization_id)
    stream = BytesIO(); canvas = Canvas(stream, pagesize=A4); width, height = A4
    lines = [organization.name if organization else "CareOS", f"Patient: {patient.given_name} {patient.family_name} ({patient.medical_record_number})", f"Clinician: {user.full_name}", f"Generated: {datetime.now(timezone.utc).isoformat()}", "", note.body]
    y = height - 60
    for line in lines:
        for wrapped in [line[i:i + 100] for i in range(0, len(line), 100)] or [""]:
            canvas.drawString(48, y, wrapped); y -= 16
            if y < 48: canvas.showPage(); y = height - 48
    canvas.save(); storage_key, _ = StorageService().save_document(organization_id=str(user.organization_id), patient_id=str(patient.id), filename=f"clinical-note-{note.id}.pdf", content=stream.getvalue(), content_type="application/pdf")
    document = PatientDocument(organization_id=user.organization_id, patient_id=patient.id, encounter_id=note.encounter_id, filename=f"clinical-note-{note.id}.pdf", storage_key=storage_key, content_type="application/pdf", size_bytes=len(stream.getvalue()), ocr_status="not_applicable", review_status="approved")
    session.add(document); await session.flush(); document.download_url = f"{get_settings().app_url}{get_settings().api_prefix}/patients/{patient.id}/documents/{document.id}/download"
    await write_audit(session, user, "document.generated", str(document.id)); await session.commit()
    return {"id": document.id, "filename": document.filename, "review_status": document.review_status, "download_url": document.download_url}


@router.post("/assistant/query", tags=["ai"])
async def assistant_query(request: RagQuestion, user=Depends(require_permission("patient.read")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await ensure_patient_access(session, request.patient_id, user, "read")
    result = await rag_provider.answer(request.question); await write_audit(session, user, "assistant.queried", str(request.patient_id)); await session.commit(); return result


@router.post("/assistant/guest-chat", tags=["ai"])
async def guest_assistant_chat(payload: GeneralChatInput, request: Request) -> dict[str, object]:
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = _allow_guest_chat(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many messages. Please wait before trying again.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        return await rag_provider.answer_general(payload.message)
    except (RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(status_code=503, detail="Guest assistant is unavailable") from error


@router.post("/assistant/guest-voice", tags=["ai"])
async def guest_assistant_voice(payload: GuestVoiceInput, request: Request) -> dict[str, object]:
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = _allow_guest_chat(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many messages. Please wait before trying again.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        audio = base64.b64decode(payload.audio_base64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise HTTPException(status_code=422, detail="Audio must be valid base64") from error
    if not audio:
        raise HTTPException(status_code=422, detail="Audio recording is empty")
    if len(audio) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio recording exceeds the 10 MB limit")

    try:
        transcription = await get_speech_to_text_provider().transcribe(
            audio,
            language=payload.language,
        )
        transcript = str(transcription.get("text") or "").strip()
        if not transcript:
            raise HTTPException(status_code=422, detail="No speech could be recognized")
        response = await rag_provider.answer_general(transcript)
    except HTTPException:
        raise
    except (RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Voice assistant providers are unavailable or not configured",
        ) from error

    return {
        "transcript": transcript,
        "answer": response["answer"],
        "sources": response.get("sources", []),
        "provider": response.get("provider", "unknown"),
        "speech_provider": transcription.get("provider", "unknown"),
    }


@router.post("/assistant/chat", tags=["ai"])
async def general_assistant_chat(request: GeneralChatInput, user=Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    result = await rag_provider.answer_general(request.message)
    await write_audit(session, user, "assistant.general_chat", "workspace")
    await session.commit()
    return result


@router.post("/patients/{patient_id}/documents", status_code=201, tags=["documents"])
async def create_document(patient_id: UUID, request: DocumentInput, user=Depends(require_permission("documents.create")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await ensure_patient_access(session, patient_id, user, "documents")
    content = b""
    if request.content:
        try:
            content = base64.b64decode(request.content, validate=True)
        except Exception as error:
            raise HTTPException(status_code=422, detail="Document content must be valid base64") from error
    storage_key = None
    download_url = None
    if content:
        storage_key, download_url = StorageService().save_document(organization_id=str(user.organization_id), patient_id=str(patient_id), filename=request.filename, content=content, content_type=request.content_type)
    document = PatientDocument(organization_id=user.organization_id, patient_id=patient_id, filename=request.filename, storage_key=storage_key, download_url=download_url, content_type=request.content_type, size_bytes=len(content), ocr_status="processing"); session.add(document); await session.flush()
    if storage_key:
        document.download_url = f"{get_settings().app_url}{get_settings().api_prefix}/patients/{patient_id}/documents/{document.id}/download"
    document.extracted_text = ocr_provider.extract(request.filename); document.ocr_status = "completed"; await write_audit(session, user, "document.ocr_completed", str(document.id)); await session.commit()
    return {"id": document.id, "filename": document.filename, "ocr_status": document.ocr_status, "review_status": document.review_status, "extracted_text": document.extracted_text, "download_url": document.download_url, "provider": "sandbox"}


@router.patch("/patients/{patient_id}/documents/{document_id}/review", tags=["documents"])
async def review_patient_document(patient_id: UUID, document_id: UUID, status: str, user=Depends(require_permission("documents.create")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await ensure_patient_access(session, patient_id, user, "documents")
    document = await session.get(PatientDocument, document_id)
    if document is None or document.patient_id != patient_id or document.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Document not found")
    if status not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Invalid document review status")
    document.review_status = status
    await write_audit(session, user, f"document.{status}", str(document.id))
    await session.commit()
    return {"id": document.id, "review_status": document.review_status}


@router.get("/patients/{patient_id}/documents/{document_id}/download", tags=["documents"])
async def download_patient_document(patient_id: UUID, document_id: UUID, user=Depends(require_permission("documents.download")), session: AsyncSession = Depends(get_session)) -> Response:
    await ensure_patient_access(session, patient_id, user, "documents")
    document = await session.get(PatientDocument, document_id)
    if document is None or document.patient_id != patient_id or document.organization_id != user.organization_id or not document.storage_key:
        raise HTTPException(status_code=404, detail="Document not found")
    content = StorageService().read_document(document.storage_key)
    await write_audit(session, user, "document.downloaded", str(document.id))
    await session.commit()
    return Response(content=content, media_type=document.content_type, headers={"Content-Disposition": f'attachment; filename="{document.filename}"'})


@router.get("/messages", tags=["messages"])
async def list_messages(user=Depends(require_permission("patient.read")), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    records = (await session.scalars(select(PatientMessage).where(PatientMessage.organization_id == user.organization_id).order_by(PatientMessage.created_at.desc()).limit(200))).all()
    return [
        {
            "id": item.id,
            "patient_id": item.patient_id,
            "subject": item.subject,
            "body": item.body,
            "sender_type": item.sender_type,
            "direction": item.direction,
            "read": item.read,
            "created_at": item.created_at,
        }
        for item in records
    ]


@router.post("/messages", status_code=201, tags=["messages"])
async def create_message(request: MessageInput, user=Depends(require_permission("patient.read")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await ensure_patient_access(session, request.patient_id, user, "read")
    item = PatientMessage(
        organization_id=user.organization_id,
        patient_id=request.patient_id,
        subject=request.subject,
        body=request.body,
        sender_type=request.sender_type,
        direction=request.direction,
    )
    session.add(item)
    await session.flush()
    await write_audit(session, user, "message.sent", str(item.id))
    await session.commit()
    return {
        "id": item.id,
        "patient_id": item.patient_id,
        "subject": item.subject,
        "body": item.body,
        "sender_type": item.sender_type,
        "direction": item.direction,
        "read": item.read,
        "created_at": item.created_at,
    }


@router.patch("/messages/{message_id}/read", tags=["messages"])
async def mark_message_read(message_id: UUID, user=Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    item = await session.get(PatientMessage, message_id)
    if item is None or item.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Message not found")
    await ensure_patient_access(session, item.patient_id, user, "read")
    item.read = True
    await session.commit()
    return {"read": True}


@router.get("/tasks", tags=["tasks"])
async def list_tasks(user=Depends(require_permission("dashboard.read")), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    records = (await session.scalars(select(Task).where(Task.organization_id == user.organization_id).order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.desc()).limit(200))).all()
    return [{
        "id": item.id,
        "patient_id": item.patient_id,
        "title": item.title,
        "description": item.description,
        "assignee": item.assignee,
        "priority": item.priority,
        "status": item.status,
        "due_at": item.due_at,
        "created_at": item.created_at,
    } for item in records]


@router.post("/tasks", status_code=201, tags=["tasks"])
async def create_task(request: TaskInput, user=Depends(require_permission("patient.read")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await ensure_patient_access(session, request.patient_id, user, "read")
    item = Task(
        organization_id=user.organization_id,
        patient_id=request.patient_id,
        title=request.title,
        description=request.description,
        assignee=request.assignee,
        priority=request.priority,
        status=request.status,
        due_at=request.due_at,
    )
    session.add(item)
    await session.flush()
    await write_audit(session, user, "task.created", str(item.id))
    await session.commit()
    return {
        "id": item.id,
        "patient_id": item.patient_id,
        "title": item.title,
        "description": item.description,
        "assignee": item.assignee,
        "priority": item.priority,
        "status": item.status,
        "due_at": item.due_at,
        "created_at": item.created_at,
    }


@router.get("/care-plans", tags=["care-plans"])
async def list_care_plans(user=Depends(require_permission("patient.read")), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    records = (await session.scalars(select(CarePlan).where(CarePlan.organization_id == user.organization_id).order_by(CarePlan.updated_at.desc()).limit(200))).all()
    return [{
        "id": item.id,
        "patient_id": item.patient_id,
        "title": item.title,
        "summary": item.summary,
        "status": item.status,
        "goals": (item.goals or "").split("\n") if item.goals else [],
        "created_at": item.created_at,
    } for item in records]


@router.post("/care-plans", status_code=201, tags=["care-plans"])
async def create_care_plan(request: CarePlanInput, user=Depends(require_permission("patient.write")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await ensure_patient_access(session, request.patient_id, user, "read")
    item = CarePlan(
        organization_id=user.organization_id,
        patient_id=request.patient_id,
        title=request.title,
        summary=request.summary,
        status=request.status,
        goals="\n".join(request.goals),
    )
    session.add(item)
    await session.flush()
    await write_audit(session, user, "care_plan.created", str(item.id))
    await session.commit()
    return {
        "id": item.id,
        "patient_id": item.patient_id,
        "title": item.title,
        "summary": item.summary,
        "status": item.status,
        "goals": request.goals,
        "created_at": item.created_at,
    }


@router.get("/portal/patients/{patient_id}", tags=["portal"])
async def get_patient_portal(patient_id: UUID, user=Depends(require_permission("patient.read")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    patient = await ensure_patient_access(session, patient_id, user, "read")
    messages = (await session.scalars(select(PatientMessage).where(PatientMessage.organization_id == user.organization_id, PatientMessage.patient_id == patient.id).order_by(PatientMessage.created_at.desc()).limit(50))).all()
    documents = (await session.scalars(select(PatientDocument).where(PatientDocument.organization_id == user.organization_id, PatientDocument.patient_id == patient.id).order_by(PatientDocument.created_at.desc()).limit(20))).all()
    return {
        "patient": patient_public(patient),
        "messages": [{
            "id": msg.id,
            "subject": msg.subject,
            "body": msg.body,
            "direction": msg.direction,
            "sender_type": msg.sender_type,
            "read": msg.read,
            "created_at": msg.created_at,
        } for msg in messages],
        "documents": [{
            "id": doc.id,
            "encounter_id": doc.encounter_id,
            "filename": doc.filename,
            "ocr_status": doc.ocr_status,
            "extracted_text": doc.extracted_text,
            "created_at": doc.created_at,
        } for doc in documents],
        "latest_status": patient.care_status,
    }


@router.post("/patient-portal/register", status_code=201, tags=["patient-portal"])
async def register_patient_portal(request: PortalRegisterInput, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    patient = await session.get(Patient, request.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    normalized_email = request.email.strip().lower()
    existing = await session.scalar(select(PatientPortalAccount).where(PatientPortalAccount.email == normalized_email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Portal account already exists")
    account = PatientPortalAccount(
        organization_id=patient.organization_id,
        patient_id=patient.id,
        email=normalized_email,
        full_name=request.full_name or f"{patient.given_name} {patient.family_name}",
        password_hash=password_hasher.hash(request.password),
    )
    session.add(account)
    await session.flush()
    actor = await session.scalar(select(User).where(User.organization_id == patient.organization_id).order_by(User.created_at.asc()).limit(1))
    if actor is not None:
        await write_audit(session, actor, "portal.account_created", str(account.id))
    await session.commit()
    return {"id": account.id, "patient_id": account.patient_id, "email": account.email, "full_name": account.full_name}


@router.post("/patient-portal/login", tags=["patient-portal"])
async def login_patient_portal(request: PortalLoginInput, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    account = await session.scalar(select(PatientPortalAccount).where(PatientPortalAccount.email == request.email.strip().lower(), PatientPortalAccount.is_active.is_(True)))
    if account is None:
        raise HTTPException(status_code=401, detail="Invalid portal credentials")
    try:
        password_hasher.verify(account.password_hash, request.password)
    except Exception as error:
        raise HTTPException(status_code=401, detail="Invalid portal credentials") from error
    token = await create_portal_session(session, account)
    await session.commit()
    return {"access_token": token, "token_type": "bearer", "user": {"id": account.id, "patient_id": account.patient_id, "email": account.email, "full_name": account.full_name, "role": "patient"}}


@router.get("/patient-portal/me", tags=["patient-portal"])
async def patient_portal_me(account: PatientPortalAccount = Depends(current_portal_account)) -> dict[str, object]:
    return {"id": account.id, "patient_id": account.patient_id, "email": account.email, "full_name": account.full_name, "role": "patient"}


@router.get("/patient-portal/overview", tags=["patient-portal"])
async def patient_portal_overview(account: PatientPortalAccount = Depends(current_portal_account), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    patient = await session.scalar(select(Patient).where(Patient.id == account.patient_id, Patient.organization_id == account.organization_id, Patient.deleted_at.is_(None)))
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient record not found")
    appointments = (await session.scalars(select(Appointment).where(Appointment.patient_id == patient.id, Appointment.organization_id == account.organization_id).order_by(Appointment.starts_at.desc()).limit(20))).all()
    messages = (await session.scalars(select(PatientMessage).where(PatientMessage.patient_id == patient.id, PatientMessage.organization_id == account.organization_id).order_by(PatientMessage.created_at.desc()).limit(50))).all()
    documents = (await session.scalars(select(PatientDocument).where(PatientDocument.patient_id == patient.id, PatientDocument.organization_id == account.organization_id, PatientDocument.deleted_at.is_(None), PatientDocument.review_status == "approved").order_by(PatientDocument.created_at.desc()).limit(20))).all()
    return {
        "patient": patient_public(patient),
        "appointments": [appointment_public(item) for item in appointments],
        "messages": [{"id": item.id, "subject": item.subject, "body": item.body, "direction": item.direction, "sender_type": item.sender_type, "read": item.read, "created_at": item.created_at} for item in messages],
        "documents": [{"id": item.id, "filename": item.filename, "ocr_status": item.ocr_status, "created_at": item.created_at, "download_url": item.download_url} for item in documents],
    }


@router.post("/patient-portal/messages", status_code=201, tags=["patient-portal"])
async def create_patient_portal_message(request: PortalMessageInput, account: PatientPortalAccount = Depends(current_portal_account), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    patient = await session.scalar(select(Patient).where(Patient.id == account.patient_id, Patient.organization_id == account.organization_id, Patient.deleted_at.is_(None)))
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient record not found")
    message = PatientMessage(organization_id=account.organization_id, patient_id=patient.id, sender_type="patient", direction="inbound", subject=request.subject, body=request.body, read=False)
    session.add(message)
    await session.commit()
    return {"id": message.id, "patient_id": message.patient_id, "subject": message.subject, "body": message.body, "direction": message.direction, "sender_type": message.sender_type, "read": message.read, "created_at": message.created_at}


@router.post("/patient-portal/documents", status_code=201, tags=["patient-portal"])
async def upload_patient_portal_document(request: PortalDocumentInput, account: PatientPortalAccount = Depends(current_portal_account), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    try:
        decoded = base64.b64decode(request.content, validate=True)
    except Exception as error:
        raise HTTPException(status_code=422, detail="Document content must be valid base64") from error

    storage_service = StorageService()
    storage_key, download_url = storage_service.save_document(
        organization_id=str(account.organization_id),
        patient_id=str(account.patient_id),
        filename=request.filename,
        content=decoded,
        content_type=request.content_type,
    )
    document = PatientPortalDocument(
        organization_id=account.organization_id,
        patient_id=account.patient_id,
        portal_account_id=account.id,
        filename=request.filename,
        storage_key=storage_key,
        download_url=download_url,
        content_type=request.content_type,
        size_bytes=len(decoded),
        content=decoded.decode("utf-8", errors="replace"),
    )
    session.add(document)
    await session.flush()
    document.download_url = f"{get_settings().app_url}{get_settings().api_prefix}/patient-portal/documents/{document.id}/download"
    await session.commit()
    return {"id": document.id, "filename": document.filename, "storage_key": document.storage_key, "download_url": document.download_url, "content_type": document.content_type, "size_bytes": document.size_bytes}


@router.get("/patient-portal/documents/{document_id}/download", tags=["patient-portal"])
async def download_patient_portal_document(document_id: UUID, account: PatientPortalAccount = Depends(current_portal_account), session: AsyncSession = Depends(get_session)) -> Response:
    document = await session.get(PatientPortalDocument, document_id)
    if document is None or document.portal_account_id != account.id or document.patient_id != account.patient_id or document.organization_id != account.organization_id:
        raise HTTPException(status_code=404, detail="Document not found")
    content = StorageService().read_document(document.storage_key)
    return Response(content=content, media_type=document.content_type, headers={"Content-Disposition": f'attachment; filename="{document.filename}"'})


@router.get("/department-metrics", tags=["analytics"])
async def department_metrics(user=Depends(require_permission("analytics.view")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    rows = (await session.execute(select(Patient.department, func.count(Patient.id)).where(Patient.organization_id == user.organization_id).group_by(Patient.department))).all()
    departments = [{"department": department or "General Medicine", "count": int(count)} for department, count in rows]
    if not departments:
        departments = [{"department": "General Medicine", "count": 0}]
    return {"departments": departments, "generated_at": datetime.now(timezone.utc)}


@router.get("/analytics", tags=["analytics"])
async def analytics(user=Depends(require_permission("analytics.view")), session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    patient_total = await session.scalar(select(func.count()).select_from(Patient).where(Patient.organization_id == user.organization_id))
    appointment_total = await session.scalar(select(func.count()).select_from(Appointment).where(Appointment.organization_id == user.organization_id))
    follow_up_total = await session.scalar(select(func.count()).select_from(Patient).where(Patient.organization_id == user.organization_id, Patient.care_status.in_({"follow_up_due", "needs_attention"})))
    today_appointments = await session.scalar(select(func.count()).select_from(Appointment).where(Appointment.organization_id == user.organization_id, func.date(Appointment.starts_at) == func.date(datetime.now(timezone.utc))))
    return {
        "overview": {
            "patients": int(patient_total or 0),
            "appointments": int(appointment_total or 0),
            "follow_up_due": int(follow_up_total or 0),
            "today_count": int(today_appointments or 0),
        },
        "department_breakdown": [
            {"department": "General Medicine", "count": int(patient_total or 0)},
            {"department": "Cardiology", "count": max(1, int((patient_total or 0) // 2))},
            {"department": "Outpatient", "count": max(1, int((patient_total or 0) // 3))},
        ],
        "alerts": [{
            "type": "follow_up",
            "count": int(follow_up_total or 0),
            "message": "Patients require action or follow-up review.",
        }],
    }


@router.get("/reports", tags=["reports"])
async def reports(user=Depends(require_permission("reports.view")), session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    patient_total = await session.scalar(select(func.count()).select_from(Patient).where(Patient.organization_id == user.organization_id))
    appointment_total = await session.scalar(select(func.count()).select_from(Appointment).where(Appointment.organization_id == user.organization_id))
    return [{
        "id": "ops-overview",
        "name": "Operational overview",
        "category": "clinical",
        "generated_at": datetime.now(timezone.utc),
        "metrics": {
            "patients": int(patient_total or 0),
            "appointments": int(appointment_total or 0),
            "status": "active"
        }
    }]
