# Journeys

| Journey | File | Covers | Priority | Graph nodes touched | Assertion points | Failure modes |
| ------- | ---- | ------ | -------- | ------------------- | ---------------- | ------------- |
| J-01 Full End-to-End Self-Service Account Opening | `journey_01_account-opening.md` | AS-01 | critical | `ui_mobile_app`, `api_gateway`, `onboarding_service`, `identity_service`, `bank_adapter_service`, `audit_service`, `db_postgres`, `cache_redis`, `bank_submission_queue`, `bank_submission_worker`, `application_submitted_event`, `fayda_ekyc_api`, `bank_cbs_api` | 7 | 3 |
| J-02 User Refuses Consent Halts Flow | `journey_02_consent-refusal.md` | AS-02 | high | `ui_mobile_app`, `api_gateway`, `onboarding_service`, `audit_service`, `db_postgres`, `cache_redis` | 4 | 2 |
| J-03 Invalid Fayda National ID Format Lockout | `journey_03_fayda-format-lockout.md` | AS-03 | high | `ui_mobile_app`, `api_gateway`, `onboarding_service`, `identity_service`, `audit_service`, `db_postgres`, `cache_redis` | 5 | 1 |
| J-04 OTP Verification Retry Exhaustion Branch Fallback | `journey_04_otp-retry-fallback.md` | AS-04 | critical | `ui_mobile_app`, `api_gateway`, `onboarding_service`, `identity_service`, `audit_service`, `db_postgres`, `cache_redis`, `fayda_ekyc_api` | 5 | 2 |
| J-05 Facial Liveness Spoof Detection Rejection | `journey_05_liveness-spoof-rejection.md` | AS-05 | critical | `ui_mobile_app`, `api_gateway`, `onboarding_service`, `identity_service`, `audit_service`, `db_postgres`, `cache_redis` | 4 | 2 |
| J-06 Dynamic Bank Field Schema Validation Failure | `journey_06_dynamic-fields-validation.md` | AS-06 | normal | `ui_mobile_app`, `api_gateway`, `onboarding_service`, `bank_adapter_service`, `db_postgres`, `cache_redis` | 4 | 1 |
| J-07 Idempotent Submission Handling Transient Bank Offline | `journey_07_bank-offline-retry.md` | AS-07 | critical | `ui_mobile_app`, `api_gateway`, `onboarding_service`, `bank_adapter_service`, `audit_service`, `db_postgres`, `cache_redis`, `bank_submission_queue`, `bank_submission_worker`, `application_submitted_event`, `bank_cbs_api` | 5 | 2 |
| J-08 Asynchronous Bank Callback and Account Number Issuance | `journey_08_async-bank-callback.md` | AS-08 | high | `ui_mobile_app`, `api_gateway`, `onboarding_service`, `audit_service`, `db_postgres`, `cache_redis` | 5 | 2 |

## Uncovered graph nodes
none
