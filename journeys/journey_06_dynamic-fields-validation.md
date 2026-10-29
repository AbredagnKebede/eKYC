# Journey: Dynamic Bank Field Schema Validation Failure
journey_id: J-06
covers: AS-06
priority: normal
graph_nodes: [ui_mobile_app, api_gateway, onboarding_service, bank_adapter_service, db_postgres, cache_redis]

## User Steps (black-box perspective)

1. User successfully passes Fayda OTP and biometric liveness checks and proceeds to the bank details screen for "Awash Bank".
2. App fetches the bank's active dynamic schema requiring `occupation`, `monthly_income_range`, and `source_of_funds`.
3. User leaves `source_of_funds` empty or enters an invalid data type (e.g., string in a numeric field) and attempts to submit the form.
4. App highlights the invalid inputs with localized schema validation messages and blocks progression.
5. If an invalid payload is sent directly to the API, the system returns HTTP 400 Problem Details specifying the exact missing JSONSchema properties, keeping the application in state `LIVENESS_PASSED`.

## Required System Components (what must be running)

- `api` — API Gateway running Pydantic dynamic JSONSchema validation against registered partner bank schemas.
- `postgres` — PostgreSQL database holding application records.

## Assertion Points (what proves this worked)

- AP-1 API response: `PUT /v1/applications/{id}/details` returns HTTP 400 Bad Request with field-level validation errors.
- AP-2 Database: `applications` status remains `LIVENESS_PASSED`; does not advance to `DATA_COMPLETE`.
- AP-3 Database: `bank_submissions` has 0 rows for this application ID.
- AP-4 Queue: Zero messages are enqueued onto `bank_submission_queue`.

## Failure Modes to Test

- CH-03 Modifying bank JSONSchema definition dynamically while an application is in flight safely triggers re-validation against the updated schema version.
