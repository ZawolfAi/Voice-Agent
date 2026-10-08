# Booking Agent Testing Audit

This audit covers `tests/test_booking_agent_real_workflow.py` plus the existing Booking coverage
in `tests/test_agent_service_integration.py`.

## Database Isolation

The backend test configuration sets `APP_ENV=test` and points `DATABASE_URL` at a process-scoped
SQLite database under `/tmp` from `tests/conftest.py`. The Booking real-workflow tests explicitly
initialize that schema before direct service/session tests, so they do not use `backend/careos.db`
or production data.

## Test Classification

| Test | Type | Agent mocked | Tool mocked | Service mocked | DB/session mocked | External LLM mocked | Persisted DB assertion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `test_booking_agent_unit_actions_call_tools[...]` | UNIT | No | Yes, `RecordingBookingTools` | N/A | N/A | N/A | No |
| `test_booking_agent_unit_missing_fields_confirmation_rejection_and_unknown` | UNIT | No | N/A | N/A | N/A | N/A | No |
| `test_booking_agent_unit_availability_collection_and_invalid_input` | UNIT | No | Yes, `RecordingBookingTools` | N/A | N/A | N/A | No |
| `test_booking_agent_unit_failed_execution_without_tool_call` | UNIT | No | Yes, recording mock verifies no call | N/A | N/A | N/A | No |
| `test_booking_agent_unit_does_not_access_database_or_http` | UNIT | No | N/A | N/A | N/A | N/A | No |
| `test_booking_tools_unit_do_not_duplicate_service_database_logic` | TOOL | N/A | No | N/A | N/A | N/A | No |
| `test_booking_tools_unit_delegate_to_services_and_preserve_context` | TOOL | N/A | No | Yes | Yes, object sentinel | N/A | No |
| `test_booking_service_create_read_modify_cancel_and_persist` | SERVICE | N/A | N/A | No | No | N/A | Yes |
| `test_booking_service_boundaries_conflicts_and_invalid_statuses` | SERVICE | N/A | N/A | No | No | N/A | Yes, for setup record |
| `test_booking_agent_to_tool_to_service_to_database_real_chain` | INTEGRATION | No | No | No | No | N/A | Yes |
| `test_booking_e2e_arabic_request_collects_availability_confirms_and_persists` | E2E | No | No | No | No | Yes, extraction represented as structured output only | Yes |
| `test_booking_real_lifecycle_create_read_modify_and_create_cancel` | INTEGRATION | N/A | No | No | No | N/A | Yes |
| `test_booking_tools_create_reschedule_cancel_and_reject_occupied_slot` | INTEGRATION | N/A | No | No | No | N/A | Yes |
| `test_agent_tools_enforce_patient_authorization` | INTEGRATION | N/A | No | No | No | N/A | No write expected; verifies rejection |

## False Confidence Risks

The unit tests intentionally mock the tool layer, so they prove state management, missing-field
collection, confirmation/rejection, availability handoff, invalid input, failed execution, and the
absence of direct database/HTTP behavior. They do not prove persistence.

The tool delegation test intentionally mocks appointment service functions. It proves correct
parameter/context handoff and that the tool does not duplicate SQLAlchemy persistence logic.

Persistence confidence comes from the service, integration, lifecycle, and E2E tests. Those tests
use real `BookingTools`, real appointment service functions, real SQLAlchemy async sessions, and
directly query `Appointment` rows after mutations.
