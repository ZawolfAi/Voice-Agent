"""Production SAML service-provider boundary for hospital identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import get_settings


@dataclass(frozen=True)
class SAMLIdentity:
    email: str
    full_name: str
    provider_user_id: str
    organization_domain: str | None = None
    role: str | None = None


class HospitalSAMLProvider:
    """Use python3-saml for signed assertion validation and SSO requests."""

    def __init__(self, *, organization_domain: str, idp_settings: dict[str, Any]) -> None:
        self.organization_domain = organization_domain
        self.idp_settings = idp_settings

    def _auth(self, request_data: dict[str, Any]):
        try:
            from onelogin.saml2.auth import OneLogin_Saml2_Auth
        except ImportError as error:
            raise RuntimeError("python3-saml is required for SAML production sign-in") from error
        return OneLogin_Saml2_Auth(request_data, self.idp_settings)

    def login_url(self, request_data: dict[str, Any]) -> str:
        return self._auth(request_data).login()

    def parse_response(self, request_data: dict[str, Any], saml_response: str) -> SAMLIdentity:
        auth = self._auth(request_data)
        auth.process_response(saml_response)
        errors = auth.get_errors()
        if errors:
            raise ValueError(f"SAML assertion validation failed: {','.join(errors)}")
        if not auth.is_authenticated():
            raise ValueError("SAML identity is not authenticated")
        attributes = auth.get_attributes()
        email = auth.get_nameid() or (attributes.get("email") or [None])[0]
        if not email:
            raise ValueError("SAML assertion is missing an email")
        full_name = (attributes.get("name") or [email.split("@", 1)[0]])[0]
        role = (attributes.get("role") or [None])[0]
        return SAMLIdentity(
            email=str(email).lower(),
            full_name=str(full_name),
            provider_user_id=str(auth.get_nameid() or email),
            organization_domain=self.organization_domain,
            role=str(role).lower() if role else None,
        )


def saml_is_configured() -> bool:
    settings = get_settings()
    return bool(settings.saml_metadata_url)
