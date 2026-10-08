# Follow-Up Agent Testing Audit

This audit covers the Follow-Up workflow tests in `tests/test_followup_agent_real_workflow.py`
and the existing adjacent integration coverage in `tests/test_agent_service_integration.py`.

## Database Isolation

The backend test environment sets `APP_ENV=test` and points `DATABASE_URL` at a process-scoped
SQLite database in `/tmp` from `tests/conftest.py`. The Follow-Up real-workflow tests explicitly
initialize that schema before direct service/session tests, so they do not use `backend/careos.db`
or production data.

## Test Classification

| Test | Type | Agent mocked | Tool mocked | Service mocked | DB/session mocked | External LLM mocked | Persisted DB assertion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `test_followup_agent_unit_actions_call_tools[...]` | UNIT | No | Yes, `RecordingFollowUpTools` | N/A | N/A | N/A | No |
| `test_followup_agent_unit_missing_fields_confirmation_and_rejection` | UNIT | No | N/A | N/A | N/A | N/A | No |
| `test_followup_agent_unit_invalid_uuid_fails_without_tool_call` | UNIT | No | Yes, recording mock verifies no call | N/A | N/A | N/A | No |
| `test_followup_agent_unit_unknown_intent_is_not_executable` | UNIT | No | N/A | N/A | N/A | N/A | No |
| `test_followup_agent_unit_does_not_access_database_directly` | UNIT | No | N/A | N/A | N/A | N/A | No |
| `test_followup_tools_unit_do_not_duplicate_service_database_logic` | TOOL | N/A | No | N/A | N/A | N/A | No |
| `test_followup_tools_unit_delegate_to_services_and_preserve_context` | TOOL | N/A | No | Yes | Yes, object sentinel | N/A | No |
| `test_followup_service_create_get_modify_complete_cancel_and_persist` | SERVICE | N/A | N/A | No | No | N/A | Yes |
| `test_followup_service_boundaries_invalid_and_appointment_relationship` | SERVICE | N/A | N/A | No | No | N/A | Yes |
| `test_followup_agent_to_tool_to_service_to_database_create_real_chain` | INTEGRATION | No | No | No | No | N/A | Yes |
| `test_followup_e2e_arabic_request_with_mocked_llm_persists_record` | E2E | No | No | No | No | Yes, extractor only | Yes |
| `test_followup_real_lifecycle_create_get_modify_complete_and_create_cancel` | INTEGRATION | N/A | No | No | No | N/A | Yes |
| `test_followup_tools_enforce_patient_authorization_real_db` | INTEGRATION | N/A | No | No | No | N/A | No write expected; verifies rejection |
| `test_followup_tools_create_read_update_and_status` | INTEGRATION | N/A | No | No | No | N/A | Yes |
| `test_agent_tools_enforce_patient_authorization` | INTEGRATION | N/A | No | No | No | N/A | No write expected; verifies rejection |

## False Confidence Risks

The pure agent tests intentionally mock the tool layer, so they prove state transitions, action
selection, confirmation/rejection handling, invalid UUID handling, and no direct database access.
They do not prove persistence.

The tool delegation test intentionally mocks service functions, so it proves parameter/context
handoff but does not prove business rules or persistence.

Persistence confidence comes from the service, integration, lifecycle, and E2E tests listed above.
Those tests use the real `FollowUpService`, real `FollowUpTools`, real SQLAlchemy async sessions,
and query `FollowUp` records after execution.
