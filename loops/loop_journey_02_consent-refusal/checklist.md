# Journey Checklist: loop_journey_02_consent-refusal

- [ ] AP-1 Application state transitions directly to CANCELLED in database
- [ ] AP-2 Zero requests are sent to Fayda eKYC API or any external identity provider
- [ ] AP-3 Zero personal demographic data, biometric artifacts, or identifiers are recorded in persistence
- [ ] AP-4 Audit log contains CONSENT_REFUSED record with client device fingerprint and timestamp
- [ ] 100% of assertion points verified by black-box tests in tests/journey/j02
- [ ] Zero mocks at critical boundaries (db)
- [ ] Real processes and sandbox services running
