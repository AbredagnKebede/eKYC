# Spec Amendments

## AMD-001 — Bank portal Fast Forward and Fayda-first passport (2026-11-09)

### Application status extensions

Add:

- `AWAITING_BANK_OUTBOUND` — customer submitted; bank must confirm before CBS when `ff_outbound` is off.
- `CBS_PENDING_BANK_RELEASE` — CBS responded; bank must confirm/edit before customer sees final status when `ff_inbound` is off.

Legal transitions (additions):

- `DATA_COMPLETE` → `AWAITING_BANK_OUTBOUND` | `SUBMITTED_TO_BANK`
- `AWAITING_BANK_OUTBOUND` → `SUBMITTED_TO_BANK` | `CANCELLED` | `EXPIRED`
- `SUBMITTED_TO_BANK` → `CBS_PENDING_BANK_RELEASE` | `ACCOUNT_OPENED` | `BANK_REJECTED` | `BANK_ACCEPTED`
- `CBS_PENDING_BANK_RELEASE` → `ACCOUNT_OPENED` | `BANK_REJECTED`

### Bank settings

Per `bank_id`:

- `ff_outbound` (bool) — auto-forward customer submissions to CBS
- `ff_inbound` (bool) — auto-release CBS outcomes to the customer app

### Bank staff RBAC

Roles scoped to one `bank_id`: `SUPER_ADMIN` > `ADMIN` > `EMPLOYEE`.

### Fayda-first passport

Customer Passport identity is established via Fayda OTP before bank selection; listing is scoped by `fayda_ref_hash` (and device binding), not anonymous device-only `user_ref`.
