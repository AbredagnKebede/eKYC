# Fayda Onboard — Improvement Brief

**Goal:** Turn the one-shot onboarding wizard into a bank-ready product: Fayda-bound customer home, credible biometrics, bank ops, and production-grade status delivery.  
**Boundary:** We remain an onboarding agent — no balances, deposits, or CBS replacement.

---

## Product north star

**Fayda Banking Passport** — one Fayda-verified profile; many independent bank journeys; track opened vs in-flight applications; resume without restarting.

| Surface | What the customer sees |
|---------|------------------------|
| Identity | Fayda-verified session (no raw FIN) |
| Journeys | Per-bank cards with status + Resume |
| Opened | Masked account #, tier, activation link/instructions |
| Timeline | Human events: OTP → submitted → issued / rejected |

---

## Improvement plan (priority order)

| # | Workstream | Outcome | Doable now? | Status |
|---|------------|---------|-------------|--------|
| 1 | **Passport home** | List applications + accounts; start another bank | Yes | **Done** — `GET /v1/applications`, Flutter passport |
| 2 | **Resume-safe sessions** | Continue mid-flow; expiry + OTP lockout UX | Yes | **Done** — `resume_step` + Flutter resume + lockout copy |
| 3 | **Real liveness + face match** | ONNX anti-spoof + Fayda photo match | Partial / paid models | Deferred |
| 4 | **Bank ops console** | Pending queue, approve/reject, audit | Yes (sandbox) | **Done** — `/ops` + `/v1/ops/*` |
| 5 | **CBS webhooks + retries** | Async callback + status delivery | Yes (sandbox) | **Done** — sandbox delayed webhook |
| 6 | **Tiered products** | Real schemas per bank×tier | Yes | **Done** — `schemas_by_tier` + `?tier=` |
| 7 | **Observability + abuse** | Audit viewer, FIN/OTP lockouts | Yes | **Done** — `/v1/ops/audit` + lockout path |
| 8 | **Amharic (+ Afaan Oromo)** | Locale toggle on critical screens | Yes | **Done** — `mobile/lib/l10n/strings.dart` |
| 9 | **iOS + store distribution** | TestFlight / Play | Needs paid accounts | Deferred |
| 10 | **Bank portals + dual Fast Forward** | Per-bank Next.js portal (Vercel), RBAC, `ff_outbound`/`ff_inbound` gates | Yes | **Done** — `bank-portal/` Next.js + `/v1/bank-portal/*` |
| 11 | **Fayda-first mobile auth** | FIN+OTP before bank picker; optional app PIN lock | Yes | **Done** — passport identity routes + Flutter flow |

---

## Objective verification

```bash
# Against local Docker (API :8005)
python3 scripts/verify_improvements.py
python3 scripts/verify_bank_portal.py
```

Last local run: **ALL IMPROVEMENT CHECKS PASSED** (passport multi-bank, resume_step, tier schemas, sandbox webhook, ops queue/approve path, audit list, `/ops` HTML, lockout, l10n files).

Bank portal script covers: both FF ON auto-open, inbound hold+release, outbound queue+send, employee cannot PATCH settings, cross-bank isolation, Fayda-first passport session.

Also: `flutter analyze lib` — no errors (1 style info fixed).

---

## Verify checklist

- [x] After open, app can land on Passport (Flutter) — not only blank restart  
- [x] Two banks can be in-flight for one profile (`GET /v1/applications`)  
- [x] Resume hits the correct step via `resume_step`  
- [x] Bank can approve/reject via `/ops` (sandbox); webhook can open enterprise without poll-only  
- [ ] Liveness rejects spoofs with production ONNX — deferred (#3)  
- [x] Amharic / Afaan Oromo cover passport + core flow strings  
- [x] Dual Fast Forward gates park outbound/inbound independently  
- [x] Super Admin / Admin / Employee RBAC on bank portal  
- [x] Fayda OTP before bank selection when passport session absent  

---

## Out of scope (for now)

In-app balances, transfers, statements, credit, permanent biometric storage, plaintext FIN retention, real partner CBS endpoints, store distribution, real bank SSO.
