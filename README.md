# Fayda Onboard (eKYC)

Self-service bank onboarding for Ethiopia: verify once with **Fayda** (national ID), then open accounts at partner banks from a mobile passport.

## What’s in this repo

| Piece | Path | Role |
|-------|------|------|
| API | `src/` | FastAPI gateway, workers, bank adapters, Fayda/CBS sandboxes |
| Android client | `mobile/` | Flutter onboarding + banking passport |
| Bank staff portal | `bank-portal/` | Next.js console (queues, Fast Forward, RBAC) — deploy on Vercel |
| Tester landing | `static/testers/` | APK download + sandbox instructions (served by the API) |
| Ops console | `static/ops/` | Legacy sandbox approve/reject UI |

## Live sandbox

- **API:** https://ekyc-api-jj0j.onrender.com  
- **Health:** https://ekyc-api-jj0j.onrender.com/health  
- **Tester page:** https://ekyc-api-jj0j.onrender.com/  
- **APK:** [GitHub Releases (latest)](https://github.com/AbredagnKebede/eKYC/releases/latest)

Sandbox OTP is always `123456`. The free Render service sleeps after idle; the first request can take 30–60s.

## Customer flow (mobile)

1. Verify Fayda FIN + OTP (binds the passport)  
2. Open passport → add a bank → consent → liveness → details → sign  
3. Track status; activate when the account is issued  

Optional app PIN lock is available after passport binding.

## Bank staff portal

Next.js app in `bank-portal/` (Vercel). Set:

```text
NEXT_PUBLIC_API_BASE_URL=https://ekyc-api-jj0j.onrender.com
```

Sandbox Super Admin (example): `super@cbe.portal.local` / `ChangeMeBankPortal1!` (bank `bank_cbe`).

## Local development

```bash
# Infra + API (Docker)
docker compose up -d --build

# API is on http://127.0.0.1:8005
curl -s http://127.0.0.1:8005/health

# Flutter
cd mobile && flutter run --dart-define=API_BASE=http://10.0.2.2:8005

# Bank portal
cd bank-portal && cp .env.example .env.local && npm install && npm run dev
```

Cloud all-in-one image: `Dockerfile.cloud` + `render.yaml` (API, worker, sandboxes in one web service).

## Verification

```bash
API_BASE_URL=https://ekyc-api-jj0j.onrender.com python3 scripts/verify_live_e2e.py
API_BASE_URL=http://127.0.0.1:8005 python3 scripts/verify_bank_portal.py
```

## Docs for testers / deploy

See [DEPLOY_TESTERS.md](DEPLOY_TESTERS.md) for Render blueprint steps and APK packaging.

## License / status

Pilot sandbox — not production Fayda or partner CBS endpoints.
