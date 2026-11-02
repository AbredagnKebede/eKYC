# Journey Checklist: loop_journey_01_account-opening

- [x] AP-1 Database: applications table row has status='ACCOUNT_OPENED' and non-null idempotency_hash
- [x] AP-2 Database: identity_snapshots table row has verification_method='OTP' and encrypted demographics
- [x] AP-3 Queue: bank_submission_queue message was consumed and acknowledged by bank_submission_worker
- [x] AP-4 External API: fayda_ekyc_api sandbox received verification request and returned HTTP 200 with verified claims
- [x] AP-5 External API: bank_cbs_api sandbox received verified submission payload and returned a generated account number
- [x] AP-6 Audit: audit_logs table contains hash-chained entries for CONSENT_GRANTED, IDENTITY_VERIFIED, LIVENESS_PASSED, and APPLICATION_SUBMITTED
- [x] AP-7 Latency: Complete application submission to account issuance round-trip completes within 5.0 seconds
- [x] 100% of assertion points verified by black-box tests in tests/journey/j01
- [x] Zero mocks at critical boundaries (db, queue, external_api, worker)
- [x] Real processes and sandbox services running
