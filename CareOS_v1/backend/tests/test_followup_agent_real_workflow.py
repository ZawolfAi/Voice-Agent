import inspect
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ai.followup.agent import FollowUpAgent
from app.ai.followup.contracts import FollowUpExtraction
from app.ai.followup.extractor import FollowUpExtractor
from app.ai.followup.state import FollowUpState, build_followup_state
from app.ai.followup.tools import FollowUpTools
from app.db import init_db, session_factory
from app.main import app
from app.models import Appointment, FollowUp, Organization, Patient, User
from app.services.followups import (
    create_followup,
    get_followup,
    update_followup,
    update_followup_status,
)


def _register_user(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"followup-real-{uuid4().hex[:8]}@example.org",
            "password": "strong-password",
            "full_name": "FollowUp Real User",
            "organization_name": f"FollowUp Real Org {uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_patient(client: TestClient, token: str) -> UUID:
    response = client.post(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "medical_record_number": f"FU-{uuid4().hex[:8]}",
            "given_name": "Follow",
            "family_name": "Patient",
            "date_of_birth": "1990-01-01",
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def _load_user(user_id: str) -> User:
    async with session_factory() as session:
        user = await session.get(User, UUID(user_id))
        assert user is not None
        return user


_schema_initialized = False


async def _ensure_test_schema() -> None:
    global _schema_initialized
    if not _schema_initialized:
        await init_db()
        _schema_initialized = True


async def _make_user_and_patient() -> tuple[User, UUID]:
    await _ensure_test_schema()
    async with session_factory() as session:
        organization = Organization(name=f"FollowUp Direct Org {uuid4().hex[:6]}")
        session.add(organization)
        await session.flush()
        user = User(
            organization_id=organization.id,
            email=f"followup-direct-{uuid4().hex[:8]}@example.org",
            full_name="FollowUp Direct User",
            role="admin",
            password_hash="test-password-hash",
            onboarding_complete=True,
        )
        patient = Patient(
            organization_id=organization.id,
            medical_record_number=f"FU-DIRECT-{uuid4().hex[:8]}",
            given_name="Follow",
            family_name="Patient",
            date_of_birth=date(1990, 1, 1),
        )
        session.add_all([user, patient])
        await session.commit()
        return user, patient.id


class RecordingFollowUpTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.create_followup = AsyncMock(side_effect=self._create)
        self.get_followup = AsyncMock(side_effect=self._get)
        self.update_followup = AsyncMock(side_effect=self._update)
        self.update_followup_status = AsyncMock(side_effect=self._status)

    async def _create(self, **kwargs):
        self.calls.append(("create_followup", kwargs))
        return {"id": uuid4(), "status": "pending", **kwargs}

    async def _get(self, **kwargs):
        self.calls.append(("get_followup", kwargs))
        return {"id": kwargs["followup_id"], "status": "pending"}

    async def _update(self, **kwargs):
        self.calls.append(("update_followup", kwargs))
        return {"id": kwargs["followup_id"], "status": "pending", **kwargs}

    async def _status(self, **kwargs):
        self.calls.append(("update_followup_status", kwargs))
        return {"id": kwargs["followup_id"], "status": kwargs["status"]}


@pytest.mark.parametrize(
    ("action", "expected_tool", "extra"),
    [
        ("create", "create_followup", {"followup_type": "visit", "reason": "Check symptoms"}),
        ("get", "get_followup", {}),
        ("modify", "update_followup", {"reason": "Move later"}),
        ("cancel", "update_followup_status", {}),
        ("complete", "update_followup_status", {}),
    ],
)
@pytest.mark.asyncio
async def test_followup_agent_unit_actions_call_tools(action: str, expected_tool: str, extra: dict[str, object]) -> None:
    patient_id = uuid4()
    followup_id = uuid4()
    due_at = datetime.now(timezone.utc) + timedelta(days=7)
    state = FollowUpState(
        patient_id=str(patient_id),
        action=action,
        followup_id=str(followup_id),
        due_at=due_at,
        status="collecting",
        **extra,
    )
    if action == "create":
        state.followup_id = None

    agent = FollowUpAgent()
    state = agent.process(state)
    transitions = [state.status]
    if state.awaiting_confirmation:
        state = agent.process(state, confirmation="confirm")
        transitions.append(state.status)

    tools = RecordingFollowUpTools()
    state = await agent.execute(state, tools)
    transitions.append(state.status)

    assert state.status == "completed"
    assert tools.calls[0][0] == expected_tool
    assert transitions[-1] == "completed"


def test_followup_agent_unit_missing_fields_confirmation_and_rejection() -> None:
    agent = FollowUpAgent()
    missing = agent.process(FollowUpState(action="create", patient_id=str(uuid4())))
    assert missing.status == "collecting"
    assert set(missing.missing_fields) == {"followup_type", "reason", "due_at"}
    assert missing.awaiting_confirmation is False

    ready = agent.process(
        FollowUpState(
            action="create",
            patient_id=str(uuid4()),
            followup_type="visit",
            reason="Check symptoms",
            due_at=datetime.now(timezone.utc) + timedelta(days=4),
        )
    )
    assert ready.status == "confirming"
    assert ready.awaiting_confirmation is True

    rejected = agent.process(ready, confirmation="reject")
    assert rejected.status == "new"
    assert rejected.awaiting_confirmation is False
    assert rejected.result == {"message": "Operation rejected"}


@pytest.mark.asyncio
async def test_followup_agent_unit_invalid_uuid_fails_without_tool_call() -> None:
    tools = RecordingFollowUpTools()
    state = FollowUpState(
        action="get",
        patient_id=str(uuid4()),
        followup_id="not-a-uuid",
        status="executing",
    )

    result = await FollowUpAgent().execute(state, tools)

    assert result.status == "failed"
    assert "badly formed hexadecimal UUID" in result.error
    assert tools.calls == []


def test_followup_agent_unit_unknown_intent_is_not_executable() -> None:
    state = FollowUpAgent().process(FollowUpState(action="unknown", patient_id=str(uuid4())))
    assert state.status == "collecting"
    assert state.missing_fields == ["action"]
    assert state.awaiting_confirmation is False


def test_followup_agent_unit_does_not_access_database_directly() -> None:
    source = inspect.getsource(FollowUpAgent)

    assert "session" not in source
    assert "app.db" not in source
    assert "app.models" not in source
    assert "app.services" not in source


def test_followup_tools_unit_do_not_duplicate_service_database_logic() -> None:
    source = inspect.getsource(FollowUpTools)

    assert "session.add" not in source
    assert "session.commit" not in source
    assert "select(" not in source
    assert "from app.models" not in source


@pytest.mark.asyncio
async def test_followup_tools_unit_delegate_to_services_and_preserve_context() -> None:
    session = object()
    user = SimpleNamespace(organization_id=uuid4())
    patient_id = uuid4()
    followup_id = uuid4()
    due_at = datetime.now(timezone.utc) + timedelta(days=6)
    service_item = SimpleNamespace(
        id=followup_id,
        organization_id=user.organization_id,
        patient_id=patient_id,
        appointment_id=None,
        followup_type="call",
        reason="Check",
        due_at=due_at,
        status="pending",
    )

    with (
        patch("app.ai.followup.tools.ensure_patient_access", new_callable=AsyncMock) as access,
        patch("app.ai.followup.tools.create_followup", new_callable=AsyncMock, return_value={"id": followup_id}) as create_service,
        patch("app.ai.followup.tools.get_followup", new_callable=AsyncMock, return_value=service_item) as get_service,
        patch("app.ai.followup.tools.update_followup", new_callable=AsyncMock, return_value={"id": followup_id}) as update_service,
        patch("app.ai.followup.tools.update_followup_status", new_callable=AsyncMock, return_value={"id": followup_id, "status": "completed"}) as status_service,
    ):
        tools = FollowUpTools(session=session, user=user)

        await tools.create_followup(patient_id, "call", "Check", due_at)
        create_service.assert_awaited_once_with(
            session=session,
            organization_id=user.organization_id,
            patient_id=patient_id,
            appointment_id=None,
            followup_type="call",
            reason="Check",
            due_at=due_at,
            user=user,
        )

        await tools.get_followup(followup_id)
        await tools.update_followup(followup_id, reason="Updated")
        await tools.update_followup_status(followup_id, "completed")

        assert access.await_count == 4
        assert get_service.await_count == 3
        update_service.assert_awaited_once()
        status_service.assert_awaited_once()


@pytest.mark.asyncio
async def test_followup_service_create_get_modify_complete_cancel_and_persist() -> None:
    user, patient_id = await _make_user_and_patient()
    async with session_factory() as session:
        due_at = (datetime.now(timezone.utc) + timedelta(days=5)).replace(microsecond=0)
        created = await create_followup(
            session=session,
            organization_id=user.organization_id,
            patient_id=patient_id,
            followup_type="visit",
            reason="Initial follow-up",
            due_at=due_at,
            user=user,
        )
        followup_id = created["id"]
        db_item = await session.get(FollowUp, followup_id)
        assert db_item is not None
        assert db_item.reason == "Initial follow-up"

        fetched = await get_followup(session, followup_id=followup_id, organization_id=user.organization_id)
        assert fetched.id == followup_id

        updated_due_at = due_at + timedelta(days=2)
        await update_followup(
            session=session,
            followup_id=followup_id,
            organization_id=user.organization_id,
            due_at=updated_due_at,
            reason="Updated follow-up",
            user=user,
        )
        db_item = await session.get(FollowUp, followup_id)
        assert db_item.reason == "Updated follow-up"
        assert db_item.due_at == updated_due_at

        await update_followup_status(
            session=session,
            followup_id=followup_id,
            organization_id=user.organization_id,
            status="completed",
            user=user,
        )
        db_item = await session.get(FollowUp, followup_id)
        assert db_item.status == "completed"

        second = await create_followup(
            session=session,
            organization_id=user.organization_id,
            patient_id=patient_id,
            followup_type="call",
            reason="Cancel path",
            due_at=due_at + timedelta(days=3),
            user=user,
        )
        await update_followup_status(
            session=session,
            followup_id=second["id"],
            organization_id=user.organization_id,
            status="cancelled",
            user=user,
        )
        cancelled = await session.get(FollowUp, second["id"])
        assert cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_followup_service_boundaries_invalid_and_appointment_relationship() -> None:
    user, patient_id = await _make_user_and_patient()
    other_user, _ = await _make_user_and_patient()
    async with session_factory() as session:
        appointment = Appointment(
            organization_id=user.organization_id,
            patient_id=patient_id,
            starts_at=(datetime.now(timezone.utc) + timedelta(days=4)).replace(microsecond=0),
            reason="Source appointment",
            status="confirmed",
        )
        session.add(appointment)
        await session.commit()

        created = await create_followup(
            session=session,
            organization_id=user.organization_id,
            patient_id=patient_id,
            appointment_id=appointment.id,
            followup_type="visit",
            reason="Linked follow-up",
            due_at=(datetime.now(timezone.utc) + timedelta(days=8)).replace(microsecond=0),
            user=user,
        )
        linked = await session.get(FollowUp, created["id"])
        assert linked.appointment_id == appointment.id

        with pytest.raises(HTTPException) as missing_error:
            await get_followup(session, followup_id=uuid4(), organization_id=user.organization_id)
        assert missing_error.value.status_code == 404

        with pytest.raises(HTTPException) as org_error:
            await get_followup(session, followup_id=created["id"], organization_id=other_user.organization_id)
        assert org_error.value.status_code == 404

        with pytest.raises(HTTPException) as cross_patient_error:
            await create_followup(
                session=session,
                organization_id=other_user.organization_id,
                patient_id=patient_id,
                followup_type="call",
                reason="Cross-org patient",
                due_at=datetime.now(timezone.utc) + timedelta(days=5),
                user=other_user,
            )
        assert cross_patient_error.value.status_code == 404

        with pytest.raises(HTTPException) as cross_appointment_error:
            await create_followup(
                session=session,
                organization_id=other_user.organization_id,
                patient_id=patient_id,
                appointment_id=appointment.id,
                followup_type="visit",
                reason="Cross-org appointment",
                due_at=datetime.now(timezone.utc) + timedelta(days=5),
                user=other_user,
            )
        assert cross_appointment_error.value.status_code == 404

        with pytest.raises(HTTPException) as invalid_due:
            await create_followup(
                session=session,
                organization_id=user.organization_id,
                patient_id=patient_id,
                followup_type="call",
                reason="Past follow-up",
                due_at=datetime.now(timezone.utc) - timedelta(days=1),
                user=user,
            )
        assert invalid_due.value.status_code == 422


@pytest.mark.asyncio
async def test_followup_agent_to_tool_to_service_to_database_create_real_chain() -> None:
    user, patient_id = await _make_user_and_patient()
    due_at = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)
    state = FollowUpState(
        patient_id=str(patient_id),
        action="create",
        followup_type="call",
        reason="Check symptoms",
        due_at=due_at,
    )
    agent = FollowUpAgent()

    state = agent.process(state)
    transitions = [state.status]
    assert state.status == "confirming"

    state = agent.process(state, confirmation="confirm")
    transitions.append(state.status)
    assert state.status == "executing"

    async with session_factory() as session:
        tools = FollowUpTools(session=session, user=user)
        state = await agent.execute(state, tools)
        transitions.append(state.status)

        assert transitions == ["confirming", "executing", "completed"]
        assert state.result is not None
        db_item = await session.get(FollowUp, state.result["id"])
        assert db_item is not None
        assert db_item.patient_id == patient_id
        assert db_item.reason == "Check symptoms"
        assert db_item.status == "pending"


@pytest.mark.asyncio
async def test_followup_e2e_arabic_request_with_mocked_llm_persists_record() -> None:
    user, patient_id = await _make_user_and_patient()
    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    extraction = FollowUpExtraction(
        action="create",
        confirmation="unknown",
        followup_type="visit",
        date="بعد أسبوع",
        time="10:00",
        reason="مراجعة الأعراض",
    )

    with patch.object(FollowUpExtractor, "extract", new_callable=AsyncMock, return_value=extraction) as extract:
        parsed = await FollowUpExtractor.extract(None, "عايز أعمل متابعة للمريض بعد أسبوع")

    state = build_followup_state(
        parsed,
        patient_id=str(patient_id),
        conversation_id="conversation-1",
        timezone="Africa/Cairo",
        now=now,
    )
    agent = FollowUpAgent()
    transitions = [state.status]
    state = agent.process(state)
    transitions.append(state.status)
    state = agent.process(state, confirmation="confirm")
    transitions.append(state.status)

    async with session_factory() as session:
        tools = FollowUpTools(session=session, user=user)
        state = await agent.execute(state, tools)
        transitions.append(state.status)

        assert extract.await_count == 1
        assert transitions == ["collecting", "confirming", "executing", "completed"]
        assert state.result is not None
        db_item = await session.get(FollowUp, state.result["id"])
        assert db_item is not None
        assert db_item.patient_id == patient_id
        assert db_item.followup_type == "visit"
        assert db_item.reason == "مراجعة الأعراض"
        assert db_item.status == "pending"


@pytest.mark.asyncio
async def test_followup_real_lifecycle_create_get_modify_complete_and_create_cancel() -> None:
    user, patient_id = await _make_user_and_patient()
    async with session_factory() as session:
        tools = FollowUpTools(session=session, user=user)
        due_at = (datetime.now(timezone.utc) + timedelta(days=10)).replace(microsecond=0)

        created = await tools.create_followup(patient_id, "visit", "Lifecycle", due_at)
        fetched = await tools.get_followup(created["id"])
        assert fetched["reason"] == "Lifecycle"

        updated = await tools.update_followup(
            created["id"],
            due_at=due_at + timedelta(days=1),
            reason="Lifecycle updated",
        )
        assert updated["reason"] == "Lifecycle updated"
        db_item = await session.get(FollowUp, created["id"])
        assert db_item.reason == "Lifecycle updated"

        completed = await tools.update_followup_status(created["id"], "completed")
        assert completed["status"] == "completed"
        db_item = await session.get(FollowUp, created["id"])
        assert db_item.status == "completed"

        cancel_created = await tools.create_followup(
            patient_id,
            "call",
            "Cancel lifecycle",
            due_at + timedelta(days=2),
        )
        cancelled = await tools.update_followup_status(cancel_created["id"], "cancelled")
        assert cancelled["status"] == "cancelled"
        db_cancelled = await session.get(FollowUp, cancel_created["id"])
        assert db_cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_followup_tools_enforce_patient_authorization_real_db() -> None:
    with TestClient(app) as client:
        owner_a = _register_user(client)
        patient_a = _create_patient(client, owner_a["access_token"])
        owner_b = _register_user(client)

    user_b = await _load_user(owner_b["user"]["id"])
    async with session_factory() as session:
        tools = FollowUpTools(session=session, user=user_b)
        with pytest.raises(HTTPException) as error:
            await tools.create_followup(
                patient_id=patient_a,
                followup_type="call",
                reason="Cross-org follow-up",
                due_at=datetime.now(timezone.utc) + timedelta(days=3),
            )
        assert error.value.status_code == 404
