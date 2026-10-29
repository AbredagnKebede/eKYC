# Journey Loop: loop_journey_02_consent-refusal
journey_file: journeys/journey_02_consent-refusal.md
covers: AS-02
priority: high

## Objective
This journey loop proves end-to-end functionality for `journeys/journey_02_consent-refusal.md`.
It adds NO NEW production behavior: its sole purpose is black-box verification of what the component loops built against a real running system.

## Assertion Points to Prove
- AP-1 Application state transitions directly to CANCELLED in database
- AP-2 Zero requests are sent to Fayda eKYC API or any external identity provider
- AP-3 Zero personal demographic data, biometric artifacts, or identifiers are recorded in persistence
- AP-4 Audit log contains CONSENT_REFUSED record with client device fingerprint and timestamp

## Boundaries & Environment
- Real boundaries: `db`
- Services running: `postgres redis api`
- Required credentials: ``
