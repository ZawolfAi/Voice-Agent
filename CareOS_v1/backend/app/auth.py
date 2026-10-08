import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_session
from .models import AuthSession, AuditEvent, Organization, Permission, Role, RolePermission, User, UserRole
from .rbac import ROLE_PERMISSIONS, has_any_role, normalize_role

settings = get_settings()
password_hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=120)
    organization_name: str = Field(min_length=2, max_length=160)
    department: str = Field(default="", min_length=0, max_length=120)
    project: str = Field(default="", min_length=0, max_length=120)
    role: str = Field(default="administrator")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: str | None = None
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    mfa_recovery_code: str | None = Field(default=None, min_length=10, max_length=10)


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    department: str = Field(min_length=2, max_length=120)
    timezone: str = Field(min_length=2, max_length=80)


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(physician|doctor|nurse|care_coordinator|receptionist|hospital_director|it_admin|administrative_staff|administrator)$")


class VerifyEmailRequest(BaseModel):
    email: EmailStr


class AuditEventResponse(BaseModel):
    id: UUID
    organization_id: UUID
    actor_id: UUID
    action: str
    resource: str
    created_at: datetime

    model_config = {"from_attributes": True}


def public_user(user: User) -> dict[str, object]:
    normalized_role = normalize_role(user.role)
    effective_permissions = getattr(user, "_effective_permissions", None)
    if effective_permissions is None:
        effective_permissions = ROLE_PERMISSIONS.get(normalized_role, set())
    return {
        "id": user.id,
        "organization_id": user.organization_id,
        "department": user.department,
        "project": user.project,
        "email": user.email,
        "email_verified": bool(getattr(user, "email_verified", False)),
        "full_name": user.full_name,
        "role": normalized_role,
        "permissions": sorted(effective_permissions),
        "onboarding_complete": user.onboarding_complete,
        "mfa_enabled": bool(user.mfa_enabled),
    }


async def _token_for(session: AsyncSession, user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    jti = uuid4().hex
    session.add(AuthSession(user_id=user.id, token_jti=jti, expires_at=expires))
    await session.flush()
    return jwt.encode({"sub": str(user.id), "organization_id": str(user.organization_id), "role": user.role, "jti": jti, "exp": expires}, settings.secret_key, algorithm=settings.jwt_algorithm)


async def write_audit(session: AsyncSession, user: User, action: str, resource: str) -> None:
    session.add(AuditEvent(organization_id=user.organization_id, actor_id=user.id, action=action, resource=resource))


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), session: AsyncSession = Depends(get_session)) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_id = UUID(payload["sub"])
        jti = payload["jti"]
    except (JWTError, KeyError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from error
    auth_session = await session.scalar(select(AuthSession).where(AuthSession.token_jti == jti, AuthSession.revoked_at.is_(None)))
    user = await session.get(User, user_id)
    expires_at = auth_session.expires_at if auth_session is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if user is None or auth_session is None or expires_at is None or expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    user_permissions = await permissions_for_user(session, user)
    expected_permissions = ROLE_PERMISSIONS.get(normalize_role(user.role), set())
    if expected_permissions - user_permissions:
        await provision_role_assignments(session, user)
        await session.commit()
        user_permissions = await permissions_for_user(session, user)
    user._effective_permissions = user_permissions
    return user


async def permissions_for_user(session: AsyncSession, user: User) -> set[str]:
    assigned = (
        await session.scalars(
            select(Permission.key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user.id, Role.organization_id == user.organization_id)
        )
    ).all()
    return set(assigned)


async def provision_role_assignments(session: AsyncSession, user: User) -> None:
    role_key = normalize_role(user.role)
    role = await session.scalar(select(Role).where(Role.organization_id == user.organization_id, Role.key == role_key))
    if role is None:
        role = Role(organization_id=user.organization_id, key=role_key, name=role_key.replace("_", " ").title())
        session.add(role)
        await session.flush()
    assignment = await session.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id))
    if assignment is None:
        session.add(UserRole(user_id=user.id, role_id=role.id))
    permission_keys = ROLE_PERMISSIONS.get(role_key, set())
    existing_permissions = {
        permission.key: permission
        for permission in (await session.scalars(select(Permission).where(Permission.key.in_(permission_keys)))).all()
    }
    missing_permissions = [Permission(key=key, description="") for key in permission_keys if key not in existing_permissions]
    session.add_all(missing_permissions)
    await session.flush()
    existing_permissions.update({permission.key: permission for permission in missing_permissions})
    assigned_permission_ids = set(
        (
            await session.scalars(
                select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
            )
        ).all()
    )
    session.add_all(
        RolePermission(role_id=role.id, permission_id=permission.id)
        for permission in existing_permissions.values()
        if permission.id not in assigned_permission_ids
    )


def require_roles(*roles: str):
    async def dependency(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> User:
        assigned_roles = (
            await session.scalars(
                select(Role.key)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user.id, Role.organization_id == user.organization_id)
            )
        ).all()
        normalized_roles = {normalize_role(role) for role in roles}
        effective_roles = {normalize_role(role) for role in assigned_roles} or {normalize_role(user.role)}
        if not effective_roles.intersection(normalized_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return dependency


def require_permission(permission: str):
    async def dependency(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> User:
        permissions = await permissions_for_user(session, user)
        if permission not in permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


async def register_user(session: AsyncSession, request: RegisterRequest) -> tuple[User, str]:
    existing = await session.scalar(select(User).where(User.email == str(request.email).lower()))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    organization = Organization(name=request.organization_name, timezone="UTC")
    session.add(organization)
    await session.flush()
    user = User(
        id=uuid4(),
        organization_id=organization.id,
        department=request.department.strip(),
        project=request.project.strip(),
        email=str(request.email).lower(),
        full_name=request.full_name,
        role="admin",
        password_hash=password_hasher.hash(request.password),
    )
    session.add(user)
    await session.flush()
    await provision_role_assignments(session, user)
    await write_audit(session, user, "organization.created", request.organization_name)
    token = await _token_for(session, user)
    await session.commit()
    return user, token


async def authenticate(session: AsyncSession, request: LoginRequest) -> tuple[User, str]:
    email = str(request.email).lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    try:
        password_hasher.verify(user.password_hash, request.password)
    except Exception as error:
        raise HTTPException(status_code=401, detail="Invalid email or password") from error
    if user.mfa_enabled:
        try:
            secret = decrypt_mfa_secret(user.mfa_secret_ref or "")
        except Exception:
            secret = ""
        if request.mfa_code and verify_totp(secret, request.mfa_code):
            pass
        elif request.mfa_recovery_code and user.mfa_recovery_codes:
            recovery_hashes = json.loads(user.mfa_recovery_codes)
            candidate = hashlib.sha256(request.mfa_recovery_code.encode("ascii")).hexdigest()
            if candidate not in recovery_hashes:
                raise HTTPException(status_code=401, detail="MFA_REQUIRED")
            recovery_hashes.remove(candidate)
            user.mfa_recovery_codes = json.dumps(recovery_hashes)
        else:
            raise HTTPException(status_code=401, detail="MFA_REQUIRED")
    await provision_role_assignments(session, user)
    user._effective_permissions = await permissions_for_user(session, user)
    await write_audit(session, user, "auth.signed_in", "workspace")
    token = await _token_for(session, user)
    await session.commit()
    return user, token


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _mfa_cipher():
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_mfa_secret(secret: str) -> str:
    return _mfa_cipher().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_mfa_secret(secret_ref: str) -> str:
    return _mfa_cipher().decrypt(secret_ref.encode("ascii")).decode("ascii")


def totp_code(secret: str, timestamp: int | None = None) -> str:
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int((timestamp or int(time.time())) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify_totp(secret: str, code: str) -> bool:
    now = int(time.time())
    return any(hmac.compare_digest(totp_code(secret, now + offset), code) for offset in (-30, 0, 30))


async def revoke_token(session: AsyncSession, credentials: HTTPAuthorizationCredentials, user: User) -> None:
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[settings.jwt_algorithm])
        auth_session = await session.scalar(select(AuthSession).where(AuthSession.token_jti == payload["jti"], AuthSession.user_id == user.id))
    except (JWTError, KeyError):
        auth_session = None
    if auth_session is not None:
        auth_session.revoked_at = datetime.now(timezone.utc)
        await write_audit(session, user, "auth.signed_out", "workspace")
        await session.commit()
