# Journey Checklist: loop_journey_06_dynamic-fields-validation

- [ ] AP-1 Missing mandatory bank field triggers HTTP 400 Problem Details response listing specific missing fields
- [ ] AP-2 Invalid data type triggers HTTP 400 Problem Details indicating type mismatch
- [ ] AP-3 Application state remains in LIVENESS_PASSED and does not advance to DATA_COMPLETE
- [ ] AP-4 Valid dynamic fields payload matching bank schema returns HTTP 200 and transitions state to DATA_COMPLETE
- [ ] 100% of assertion points verified by black-box tests in tests/journey/j06
- [ ] Zero mocks at critical boundaries (db)
- [ ] Real processes and sandbox services running
