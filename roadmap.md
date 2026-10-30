# Engineering Roadmap

| Step | Loop | Type | Inputs | Outputs | Spec ref (§) | Journey ref | Verification checklist | Status |
| ---- | ---- | ---- | ------ | ------- | ------------ | ----------- | ---------------------- | ------ |
| 1 | `loop_unit_01_db-postgres` | component | `system_guide.md §2` | `src/models/base.py, src/models/application.py, src/models/audit.py, migrations/env.py` | §2 | - | tests/unit/test_db_postgres.py (≥85% coverage) | done |
| 2 | `loop_unit_02_cache-redis` | component | `system_guide.md §2, §6` | `src/infrastructure/redis.py, src/infrastructure/rate_limiter.py, src/infrastructure/session.py` | §2, §6 | - | tests/unit/test_cache_redis.py (≥85% coverage) | done |
| 3 | `loop_unit_03_audit-service` | component | `system_guide.md §6` | `src/services/audit.py, src/security/hash_chain.py` | §6 | - | tests/unit/test_audit_service.py (≥85% coverage) | done |
| 4 | `loop_unit_04_fayda-api` | component | `system_guide.md §3` | `src/clients/fayda_client.py, sandbox/fayda_sandbox.py` | §3 | - | tests/unit/test_fayda_client.py (≥85% coverage) | done |
| 5 | `loop_unit_05_identity-service` | component | `system_guide.md §3, §6` | `src/services/identity.py, src/security/encryption.py, src/security/liveness.py` | §3, §6 | - | tests/unit/test_identity_service.py (≥85% coverage) | done |
| 6 | `loop_unit_06_bank-cbs-api` | component | `system_guide.md §3` | `src/clients/bank_cbs_client.py, sandbox/bank_cbs_sandbox.py` | §3 | - | tests/unit/test_bank_cbs_client.py (≥85% coverage) | done |
| 7 | `loop_unit_07_bank-adapter-service` | component | `system_guide.md §3` | `src/services/bank_adapter.py, src/adapters/awash_finacle.py` | §3 | - | tests/unit/test_bank_adapter.py (≥85% coverage) | todo |
| 8 | `loop_unit_08_submission-queue` | component | `system_guide.md §5` | `src/infrastructure/queue.py` | §5 | - | tests/unit/test_submission_queue.py (≥85% coverage) | todo |
| 9 | `loop_unit_09_submission-event` | component | `system_guide.md §5` | `src/events/application_submitted.py` | §5 | - | tests/unit/test_submission_event.py (≥85% coverage) | todo |
| 10 | `loop_unit_10_onboarding-service` | component | `system_guide.md §4, §5` | `src/services/onboarding.py, src/state/machine.py` | §4, §5 | - | tests/unit/test_onboarding_service.py (≥85% coverage) | todo |
| 11 | `loop_unit_11_submission-worker` | component | `system_guide.md §5` | `src/workers/bank_submission.py` | §5 | - | tests/unit/test_submission_worker.py (≥85% coverage) | todo |
| 12 | `loop_unit_12_api-gateway` | component | `system_guide.md §3` | `src/api/main.py, src/api/routes/applications.py, src/api/routes/banks.py, src/api/middleware.py` | §3 | - | tests/unit/test_api_gateway.py (≥85% coverage) | todo |
| 13 | `loop_unit_13_mobile-ui` | component | `system_guide.md §1` | `ui/src/App.tsx, ui/src/components/ConsentScreen.tsx, ui/src/components/FaydaVerification.tsx, ui/src/components/LivenessCapture.tsx` | §1 | - | tests/unit/test_mobile_ui.py (≥85% coverage) | todo |
| 14 | `loop_journey_01_account-opening` | journey | `journeys/journey_01_account-opening.md`, running services | test reports | §8 | `journeys/journey_01_account-opening.md` | 100% of 7 APs (tests/journey/j01) | todo |
| 15 | `loop_journey_02_consent-refusal` | journey | `journeys/journey_02_consent-refusal.md`, running services | test reports | §8 | `journeys/journey_02_consent-refusal.md` | 100% of 4 APs (tests/journey/j02) | todo |
| 16 | `loop_journey_03_fayda-format-lockout` | journey | `journeys/journey_03_fayda-format-lockout.md`, running services | test reports | §8 | `journeys/journey_03_fayda-format-lockout.md` | 100% of 5 APs (tests/journey/j03) | todo |
| 17 | `loop_journey_04_otp-retry-fallback` | journey | `journeys/journey_04_otp-retry-fallback.md`, running services | test reports | §8 | `journeys/journey_04_otp-retry-fallback.md` | 100% of 5 APs (tests/journey/j04) | todo |
| 18 | `loop_journey_05_liveness-spoof-rejection` | journey | `journeys/journey_05_liveness-spoof-rejection.md`, running services | test reports | §8 | `journeys/journey_05_liveness-spoof-rejection.md` | 100% of 4 APs (tests/journey/j05) | todo |
| 19 | `loop_journey_06_dynamic-fields-validation` | journey | `journeys/journey_06_dynamic-fields-validation.md`, running services | test reports | §8 | `journeys/journey_06_dynamic-fields-validation.md` | 100% of 4 APs (tests/journey/j06) | todo |
| 20 | `loop_journey_07_bank-offline-retry` | journey | `journeys/journey_07_bank-offline-retry.md`, running services | test reports | §8 | `journeys/journey_07_bank-offline-retry.md` | 100% of 5 APs (tests/journey/j07) | todo |
| 21 | `loop_journey_08_async-bank-callback` | journey | `journeys/journey_08_async-bank-callback.md`, running services | test reports | §8 | `journeys/journey_08_async-bank-callback.md` | 100% of 5 APs (tests/journey/j08) | todo |
| 22 | `loop_chaos` | chaos | `system_guide.md §9`, running services | test reports | §9 | all journeys | 8 CH scenarios (tests/chaos) | todo |
