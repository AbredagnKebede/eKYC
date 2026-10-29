# Journey Loop: loop_journey_06_dynamic-fields-validation
journey_file: journeys/journey_06_dynamic-fields-validation.md
covers: AS-06
priority: normal

## Objective
This journey loop proves end-to-end functionality for `journeys/journey_06_dynamic-fields-validation.md`.
It adds NO NEW production behavior: its sole purpose is black-box verification of what the component loops built against a real running system.

## Assertion Points to Prove
- AP-1 Missing mandatory bank field triggers HTTP 400 Problem Details response listing specific missing fields
- AP-2 Invalid data type triggers HTTP 400 Problem Details indicating type mismatch
- AP-3 Application state remains in LIVENESS_PASSED and does not advance to DATA_COMPLETE
- AP-4 Valid dynamic fields payload matching bank schema returns HTTP 200 and transitions state to DATA_COMPLETE

## Boundaries & Environment
- Real boundaries: `db`
- Services running: `postgres redis api`
- Required credentials: ``
