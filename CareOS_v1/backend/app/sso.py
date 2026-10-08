"""Hospital SSO integration placeholder.

This module is the dedicated extension point for real hospital identity
provider integration. It should eventually connect to OIDC/SAML or an
internal identity provider and return normalized claims that the backend
can map to an Organization, Workspace, and User.

Implementation order for the specialist:
1. Accept an SSO start request from the web UI.
2. Generate provider redirect URL and `state` / `nonce` values.
3. Handle callback and validate JWT / token / claims.
4. Map claims to domain -> organization -> workspace.
5. Return the authenticated user payload and onboard state.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlencode

import httpx
from httpx import HTTPError
from jose import JWTError, jwt

from .config import get_settings


@dataclass(frozen=True)
class SSOClaims:
    """Normalized claims returned from a real SSO provider."""

    email: str
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    organization_domain: str | None = None
    role: str | None = None
    provider_user_id: str | None = None


class HospitalSSOAdapter:
    """Adapter for the hospital SSO contract.

    This raises the contract to a real, testable implementation while keeping
    the app safe for local development. In production, this class should be
    replaced with a real OIDC/SAML provider implementation.
    """

    def __init__(self, provider_name: str = "hospital_sso") -> None:
        settings = get_settings()
        self.provider_name = provider_name
        self.issuer_url = settings.oidc_issuer_url
        self.client_id = settings.oidc_client_id
        self.callback_url = settings.app_url or "http://localhost:5173"

    def build_redirect_url(self, *, state: str, nonce: str, redirect_uri: str | None = None) -> str:
        """Return a provider redirect URL with the required SSO state."""
        if not self.issuer_url or not self.client_id:
            raise ValueError("OIDC provider is not configured")
        redirect_target = (redirect_uri or self.callback_url).strip()
        self.validate_redirect_uri(redirect_target)
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_target,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "provider": self.provider_name,
        }
        return f"{self.issuer_url}?{urlencode(params, safe=':/?&=%')}"

    def validate_redirect_uri(self, uri: str) -> None:
        value = (uri or "").strip()
        if not value:
            raise ValueError("Redirect URI cannot be empty")
        parsed = urlparse(value)
        allowed_hosts = {host.lower().strip("[]") for host in (get_settings().sso_allowed_redirect_hosts or [])}
        host = parsed.hostname or ""
        if not host:
            raise ValueError("Redirect URI host is invalid")
        normalized_host = host.lower().strip(".")
        is_allowed_host = any(
            normalized_host == allowed or normalized_host.endswith(f".{allowed}")
            for allowed in allowed_hosts
        )
        if not is_allowed_host and parsed.netloc.lower() not in {candidate.lower() for candidate in (get_settings().sso_allowed_redirect_hosts or [])}:
            raise ValueError(f"Redirect URI host '{host}' is not allowed")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Redirect URI scheme must be http or https")

    def _decode_jwt_payload(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        padded = payload + "=" * (-len(payload) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            return json.loads(decoded)
        except (ValueError, json.JSONDecodeError):
            return {}

    def exchange_code_for_claims(self, *, code: str, state: str) -> SSOClaims:
        """Normalize a callback code into a local SSO claim set."""
        if not code or not state:
            raise ValueError("SSO callback requires both code and state")
        try:
            state_claims = jwt.decode(state, get_settings().secret_key, algorithms=[get_settings().jwt_algorithm])
            expected_nonce = str(state_claims["nonce"])
        except (JWTError, KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid or expired SSO state") from error

        try:
            if not self.issuer_url or not self.client_id:
                raise ValueError("OIDC provider is not configured")
            discovery_url = f"{self.issuer_url.rstrip('/')}/.well-known/openid-configuration"
            discovery = httpx.get(discovery_url, timeout=10)
            discovery.raise_for_status()
            metadata = discovery.json() or {}
            userinfo_endpoint = metadata.get("userinfo_endpoint")
            token_endpoint = metadata.get("token_endpoint")
            jwks_uri = metadata.get("jwks_uri")

            token_response = httpx.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "state": state,
                    "client_id": self.client_id,
                    "client_secret": get_settings().oidc_client_secret,
                    "redirect_uri": self.callback_url,
                },
                timeout=10,
            )
            token_response.raise_for_status()
            token_payload = token_response.json() or {}
            access_token = token_payload.get("access_token")
            id_token = token_payload.get("id_token")

            if get_settings().is_production:
                if not id_token or not jwks_uri:
                    raise ValueError("OIDC response is missing a verifiable ID token or JWKS URI")
                jwks_response = httpx.get(jwks_uri, timeout=10)
                jwks_response.raise_for_status()
                claims_payload = jwt.decode(
                    id_token,
                    jwks_response.json(),
                    algorithms=["RS256", "RS384", "RS512"],
                    audience=get_settings().oidc_audience or self.client_id,
                    issuer=self.issuer_url,
                )
            else:
                claims_payload = self._decode_jwt_payload(id_token) if id_token else {}
            if claims_payload.get("nonce") != expected_nonce:
                raise ValueError("OIDC nonce validation failed")
            if userinfo_endpoint and access_token:
                try:
                    userinfo = httpx.get(userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
                except TypeError:
                    userinfo = httpx.get(userinfo_endpoint, timeout=10)
                userinfo.raise_for_status()
                userinfo_payload = userinfo.json() or {}
                if userinfo_payload:
                    claims_payload = {**claims_payload, **userinfo_payload}

            if claims_payload.get("email"):
                return SSOClaims(
                    email=str(claims_payload["email"]),
                    full_name=claims_payload.get("name") or claims_payload.get("given_name", ""),
                    given_name=claims_payload.get("given_name"),
                    family_name=claims_payload.get("family_name"),
                    organization_domain=(claims_payload.get("hd") or claims_payload.get("organization_domain") or (str(claims_payload["email"]).split("@", 1)[1] if "@" in str(claims_payload["email"]) else "citycare.org")).strip().lower(),
                    role=(claims_payload.get("role") or "physician").lower(),
                    provider_user_id=str(claims_payload.get("sub") or state),
                )
        except (JWTError, HTTPError, ValueError) as error:
            if get_settings().is_production:
                raise ValueError("External identity provider exchange failed") from error

        raise ValueError("A verified external identity response is required")

    def map_claims_to_org_workspace(self, claims: SSOClaims) -> dict[str, Any]:
        """Resolve the mapped organization/workspace from SSO claims."""
        domain = (claims.organization_domain or (claims.email.split("@", 1)[1] if "@" in claims.email else "citycare.org")).strip().lower()
        org_name = domain.split(".")[0].title() + " Health"
        return {
            "organization_name": org_name,
            "organization_domain": domain,
            "workspace_name": org_name,
            "department": "General Medicine",
            "timezone": "UTC",
            "role": claims.role or "physician",
            "onboarding_complete": True,
        }
