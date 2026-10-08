"""Bi-directional synchronization client between Voice Agent and CareOS platform."""

from __future__ import annotations

import logging
from typing import Any
import uuid

import httpx

from voice_agent.app.orchestration.booking_contract import CareOSContract

logger = logging.getLogger("careos.sync")


class CareOSSyncClient:
    """Client for synchronizing Voice Agent appointments with CareOS database."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000/api/v1",
        token: str | None = None,
        department: str = "Cosmetics",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.department = department
        self.contract = CareOSContract(token=token, department=department)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def login_demo(
        self,
        role: str = "receptionist",
        username: str = "reception.demo",
        password: str = "Reception@123",
    ) -> str:
        """Authenticate with CareOS demo login to obtain a valid access token."""
        token = await CareOSContract.authenticate_with_careos(
            base_url=self.base_url,
            role=role,
            username=username,
            password=password,
        )
        self.token = token
        self.contract.token = token
        return token

    async def check_health(self) -> dict[str, Any]:
        """Verify CareOS backend liveness."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self.base_url}/health")
            resp.raise_for_status()
            return resp.json()

    async def get_appointments(
        self,
        status: str | None = None,
        from_at: str | None = None,
        to_at: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch appointments from CareOS backend."""
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if from_at:
            params["from_at"] = from_at
        if to_at:
            params["to_at"] = to_at

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.base_url}/appointments",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def create_appointment(
        self,
        patient_id: str,
        starts_at: str,
        reason: str,
        status: str = "confirmed",
    ) -> dict[str, Any]:
        """Create a new appointment in CareOS backend."""
        payload = {
            "patient_id": patient_id,
            "starts_at": starts_at,
            "reason": reason,
            "status": status,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.base_url}/appointments",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def cancel_appointment(self, appointment_id: str) -> dict[str, Any]:
        """Cancel an appointment in CareOS backend."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.patch(
                f"{self.base_url}/appointments/{appointment_id}/status?status=cancelled",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
