# Deploy for testers (free Render)

## Why this shape

Render’s free tier gives you a **web service**, **Postgres**, and **Key Value (Redis)**.  
It does **not** give free background workers — so the API, queue worker, cleanup job, and Fayda/CBS sandboxes all run inside **one** Docker web service (`Dockerfile.cloud`).

Limits to expect:
- Service **sleeps after ~15 min idle** (first open can take 30–60s)
- Free Postgres **expires after 30 days**
- 512 MB RAM — fine for pilot traffic, not production load

## 1. Push this repo to GitHub

If the remote is not set yet:

```bash
gh repo create eKYC --private --source=. --remote=origin --push
```

## 2. Deploy Blueprint on Render

1. Open [https://dashboard.render.com/blueprints](https://dashboard.render.com/blueprints)
2. **New Blueprint Instance** → select this GitHub repo
3. Render reads `render.yaml` and creates:
   - `ekyc-api` (free web)
   - `ekyc-db` (free Postgres)
   - `ekyc-kv` (free Key Value)
4. Apply → wait for the first deploy (Docker build ~5–10 min)

Your public URL will look like:

`https://ekyc-api-XXXX.onrender.com`

## 3. Build APK pointed at that URL

```bash
cd mobile
flutter build apk --release \
  --dart-define=API_BASE=https://ekyc-api-XXXX.onrender.com
cp build/app/outputs/flutter-apk/app-release.apk \
  ../static/releases/ekyc-tester.apk
```

Commit/push the APK (or upload it in Render disk / GitHub Release), then redeploy so `/static/releases/ekyc-tester.apk` is served.

Testers open:

`https://ekyc-api-XXXX.onrender.com/`

Download APK → set API base to the same origin (or keep the baked-in URL) → OTP **`123456`**.

## 4. Sanity check after deploy

```bash
curl -s https://ekyc-api-XXXX.onrender.com/health
curl -s https://ekyc-api-XXXX.onrender.com/v1/banks
API_BASE_URL=https://ekyc-api-XXXX.onrender.com \
  .venv/bin/python scripts/verify_live_e2e.py
```

## Switching to real Fayda / bank later

Only change env vars on the Render service (`FAYDA_SANDBOX_URL`, `FAYDA_API_KEY`, `BANK_CBS_SANDBOX_URL`, `BANK_API_KEY`). No app rewrite required if the wire contracts match.
