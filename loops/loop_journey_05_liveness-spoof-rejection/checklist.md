# Journey Checklist: loop_journey_05_liveness-spoof-rejection

- [x] AP-1 API response: POST /v1/applications/{id}/liveness returns HTTP 422 with spoof_detected=true and anti-spoof score < 0.90
- [x] AP-2 Database: applications status transitions strictly to LIVENESS_FAILED
- [x] AP-3 Storage: Zero raw biometric image frames or video buffers remain in ephemeral filesystem storage after evaluation
- [x] AP-4 Audit: audit_logs records LIVENESS_VERIFICATION_FAILED with model version and spoof classification score
- [x] 100% of assertion points verified by black-box tests in tests/journey/j05
- [x] Zero mocks at critical boundaries (db)
- [x] Real processes and sandbox services running
