# Journey Checklist: loop_journey_08_async-bank-callback

- [ ] AP-1 Bank webhook callback endpoint validates HMAC signature header against registered bank secret key
- [ ] AP-2 Valid callback payload updates application status to ACCOUNT_OPENED and stores issued account_number
- [ ] AP-3 Audit trail records BANK_CALLBACK_PROCESSED with bank reference identifier
- [ ] AP-4 Polling GET /v1/applications/{id} reflects ACCOUNT_OPENED status with account number and activation instructions
- [ ] AP-5 Invalid HMAC signature on webhook triggers immediate HTTP 401 and rejects state update
- [ ] 100% of assertion points verified by black-box tests in tests/journey/j08
- [ ] Zero mocks at critical boundaries (db)
- [ ] Real processes and sandbox services running
