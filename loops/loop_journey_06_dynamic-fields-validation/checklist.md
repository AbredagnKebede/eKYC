# Journey Checklist: loop_journey_06_dynamic-fields-validation

- [x] AP-1 API response: PUT /v1/applications/{id}/details returns HTTP 400 Bad Request with field-level validation errors
- [x] AP-2 Database: applications status remains LIVENESS_PASSED; does not advance to DATA_COMPLETE
- [x] AP-3 Database: bank_submissions has 0 rows for this application ID
- [x] AP-4 Queue: Zero messages are enqueued onto bank_submission_queue
- [x] 100% of assertion points verified by black-box tests in tests/journey/j06
- [x] Zero mocks at critical boundaries (db)
- [x] Real processes and sandbox services running
